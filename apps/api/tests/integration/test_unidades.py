"""Fase 1 del módulo de unidades: servicios, triggers, RLS y auditoría contra la base real."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models import AuditoriaUnidad, Membership, Persona, UnidadPersona, Unit, Vehiculo
from app.models.enums import AccionAuditoria, RelacionUnidad, TipoDocumentoIdentidad, TipoUnidad, UserRole
from app.schemas.unidades import (
    CerrarVinculoIn,
    PersonaIn,
    UnidadIn,
    UnidadUpdate,
    VehiculoIn,
    VinculoIn,
    VinculoUpdate,
)
from app.services.comun import PermisoDenegado, ValidacionError, hoy_bogota
from app.services.unidades import gestion
from tests.integration.conftest import Mundo

A = UserRole.ADMIN


async def _unidad(m: Mundo, torre: str = "1", numero: str = "101", **extra: object) -> Unit:
    actor = await m.como(A)
    return await gestion.crear_unidad(m.db, actor, UnidadIn(tower=torre, number=numero, **extra))  # type: ignore[arg-type]


def _persona(nombre: str = "Ana Gómez", doc: str | None = "1020304050", **extra: object) -> PersonaIn:
    return PersonaIn(
        nombre_completo=nombre,
        tipo_documento=TipoDocumentoIdentidad.CC if doc else None,
        numero_documento=doc,
        **extra,  # type: ignore[arg-type]
    )


# --- Unidades -------------------------------------------------------------------


async def test_crear_unidad_normaliza_y_no_duplica(mundo: Mundo) -> None:
    u = await _unidad(mundo, "Torre 2", "Apto 301", coefficient=Decimal("0.8532"))
    assert (u.tower, u.number, u.etiqueta) == ("2", "301", "2-301")
    assert u.activa and u.tipo == TipoUnidad.APARTAMENTO and u.created_at is not None
    with pytest.raises(ValidacionError, match="Ya existe la unidad 2-301"):
        await _unidad(mundo, "T2", "301")


async def test_solo_admin_gestiona(mundo: Mundo) -> None:
    aux = await mundo.como(UserRole.AUXILIAR)
    with pytest.raises(PermisoDenegado):
        await gestion.crear_unidad(mundo.db, aux, UnidadIn(number="101"))
    # Y la RLS lo impide aunque se salte el servicio
    with pytest.raises(DBAPIError, match="row-level security"):
        async with mundo.db.begin_nested():
            await mundo.db.execute(
                text("INSERT INTO units (tenant_id, tower, number) VALUES (:t, '', '999')"), {"t": mundo.tenant}
            )


async def test_anexos_de_un_solo_nivel(mundo: Mundo) -> None:
    apto = await _unidad(mundo, "1", "101")
    pq = await _unidad(mundo, "1", "PQ-01", tipo=TipoUnidad.PARQUEADERO, unidad_principal_id=apto.id)
    actor = await mundo.como(A)
    with pytest.raises(ValidacionError, match="es un anexo"):
        await gestion.crear_unidad(
            mundo.db, actor, UnidadIn(tower="1", number="DP-01", tipo=TipoUnidad.DEPOSITO, unidad_principal_id=pq.id)
        )
    otro = await _unidad(mundo, "1", "102")
    with pytest.raises(ValidacionError, match="tiene anexos"):
        await gestion.editar_unidad(mundo.db, actor, apto.id, UnidadUpdate(unidad_principal_id=otro.id))
    # El trigger lo impide también por SQL directo
    with pytest.raises(DBAPIError, match="solo se admite un nivel"):
        async with mundo.db.begin_nested():
            await mundo.db.execute(
                text("UPDATE units SET unidad_principal_id = :p WHERE id = :o"), {"p": pq.id, "o": otro.id}
            )


async def test_matricula_unica(mundo: Mundo) -> None:
    await _unidad(mundo, "1", "101", matricula_inmobiliaria="50c-123 456")
    with pytest.raises(ValidacionError, match="50C-123456 ya está en la unidad 1-101"):
        await _unidad(mundo, "1", "102", matricula_inmobiliaria="50C-123456")


async def test_cambio_de_coeficiente_exige_motivo_y_queda_auditado(mundo: Mundo) -> None:
    u = await _unidad(mundo, coefficient=Decimal("1.5"))
    actor = await mundo.como(A)
    with pytest.raises(ValidacionError, match="motivo"):
        await gestion.editar_unidad(mundo.db, actor, u.id, UnidadUpdate(coefficient=Decimal("1.6")))
    await gestion.editar_unidad(
        mundo.db, actor, u.id, UnidadUpdate(coefficient=Decimal("1.6"), motivo="Reforma del reglamento 2026")
    )
    filas = list(
        await mundo.db.scalars(
            select(AuditoriaUnidad).where(AuditoriaUnidad.entidad_id == u.id).order_by(AuditoriaUnidad.id)
        )
    )
    assert [f.accion for f in filas] == [AccionAuditoria.CREACION, AccionAuditoria.EDICION]
    assert filas[1].valores_anteriores == {"coefficient": 1.5}
    assert filas[1].valores_nuevos == {"coefficient": 1.6}
    assert filas[1].motivo == "Reforma del reglamento 2026"
    assert filas[1].usuario_id == mundo.usuarios["ADMIN"]


async def test_nada_se_borra(mundo: Mundo) -> None:
    u = await _unidad(mundo)
    await mundo.como(A)
    for tabla in ("units", "personas", "unidad_personas", "vehiculos"):
        with pytest.raises(DBAPIError, match="permission denied|No se permite eliminar"):
            async with mundo.db.begin_nested():
                await mundo.db.execute(text(f"DELETE FROM {tabla} WHERE tenant_id = :t"), {"t": mundo.tenant})  # noqa: S608
    assert await mundo.db.get(Unit, u.id) is not None


async def test_desactivar_unidad(mundo: Mundo) -> None:
    u = await _unidad(mundo)
    actor = await mundo.como(A)
    v = await gestion.vincular(
        mundo.db, actor, u.id, VinculoIn(persona=_persona(), relacion=RelacionUnidad.PROPIETARIO)
    )
    with pytest.raises(ValidacionError, match="cierre primero"):
        await gestion.desactivar_unidad(mundo.db, actor, u.id, "Unidad creada por error")
    await gestion.cerrar_vinculo(mundo.db, actor, v.id, CerrarVinculoIn(motivo="Corrección"))
    u = await gestion.desactivar_unidad(mundo.db, actor, u.id, "Unidad creada por error")
    assert not u.activa
    with pytest.raises(ValidacionError, match="desactivada"):
        await gestion.editar_unidad(mundo.db, actor, u.id, UnidadUpdate(observaciones="x"))
    u = await gestion.reactivar_unidad(mundo.db, actor, u.id, "Se desactivó por equivocación")
    assert u.activa


async def test_estado_de_coeficientes(mundo: Mundo) -> None:
    await _unidad(mundo, "1", "101", coefficient=Decimal("60"))
    await _unidad(mundo, "1", "102", coefficient=Decimal("40"))
    actor = await mundo.como(A)
    assert (await gestion.estado_coeficientes(mundo.db, actor)).cuadra
    await _unidad(mundo, "1", "103")
    estado = await gestion.estado_coeficientes(mundo.db, actor)
    assert not estado.cuadra and estado.unidades_sin_coeficiente == 1
    with pytest.raises(PermisoDenegado):
        await gestion.estado_coeficientes(mundo.db, await mundo.como(UserRole.AUXILIAR))


# --- Personas y vínculos ----------------------------------------------------------


async def test_persona_documento_unico(mundo: Mundo) -> None:
    actor = await mundo.como(A)
    p = await gestion.crear_persona(mundo.db, actor, _persona("ANA  GÓMEZ", "1.020.304.050", autoriza_datos=True))
    assert p.nombre_completo == "Ana Gómez" and p.numero_documento == "1020304050"
    assert p.autoriza_datos_at is not None
    with pytest.raises(ValidacionError, match="Ya existe una persona con CC 1020304050: Ana Gómez"):
        await gestion.crear_persona(mundo.db, actor, _persona("Otra", "1020304050"))
    # Sin documento no hay conflicto
    await gestion.crear_persona(mundo.db, actor, _persona("Sin Doc", None))
    await gestion.crear_persona(mundo.db, actor, _persona("Sin Doc Dos", None))


async def test_vinculos_automaticos_y_unicos(mundo: Mundo) -> None:
    u = await _unidad(mundo)
    actor = await mundo.como(A)
    prop = await gestion.vincular(
        mundo.db, actor, u.id, VinculoIn(persona=_persona(), relacion=RelacionUnidad.PROPIETARIO)
    )
    assert prop.es_contacto_principal and prop.responsable_pago  # el primero lo es automáticamente
    arr = await gestion.vincular(
        mundo.db,
        actor,
        u.id,
        VinculoIn(persona=_persona("Luis Pérez", "79111222"), relacion=RelacionUnidad.ARRENDATARIO, reside=True),
    )
    assert not arr.es_contacto_principal and not arr.responsable_pago
    # El arrendatario pasa a ser contacto principal: el anterior deja de serlo
    await gestion.editar_vinculo(mundo.db, actor, arr.id, VinculoUpdate(es_contacto_principal=True))
    await mundo.db.refresh(prop)
    assert not prop.es_contacto_principal and prop.responsable_pago
    with pytest.raises(ValidacionError, match="ya figura como propietario"):
        await gestion.vincular(
            mundo.db, actor, u.id, VinculoIn(persona_id=prop.persona_id, relacion=RelacionUnidad.PROPIETARIO)
        )


async def test_porcentajes_de_propiedad(mundo: Mundo) -> None:
    u = await _unidad(mundo)
    actor = await mundo.como(A)
    await gestion.vincular(
        mundo.db,
        actor,
        u.id,
        VinculoIn(persona=_persona(), relacion=RelacionUnidad.PROPIETARIO, porcentaje_propiedad=Decimal(60)),
    )
    with pytest.raises(ValidacionError, match="más del 100"):
        await gestion.vincular(
            mundo.db,
            actor,
            u.id,
            VinculoIn(
                persona=_persona("Pedro", "80123123"),
                relacion=RelacionUnidad.PROPIETARIO,
                porcentaje_propiedad=Decimal(41),
            ),
        )


async def test_cerrar_vinculo_es_historia(mundo: Mundo) -> None:
    u = await _unidad(mundo)
    actor = await mundo.como(A)
    v = await gestion.vincular(
        mundo.db,
        actor,
        u.id,
        VinculoIn(
            persona=_persona(), relacion=RelacionUnidad.PROPIETARIO, fecha_inicio=hoy_bogota() - timedelta(days=400)
        ),
    )
    with pytest.raises(ValidacionError, match="futuro"):
        await gestion.cerrar_vinculo(
            mundo.db, actor, v.id, CerrarVinculoIn(motivo="Venta", fecha_fin=hoy_bogota() + timedelta(days=1))
        )
    v = await gestion.cerrar_vinculo(mundo.db, actor, v.id, CerrarVinculoIn(motivo="Venta del apartamento"))
    assert v.fecha_fin == hoy_bogota()
    assert not v.es_contacto_principal and not v.responsable_pago  # el trigger los libera
    with pytest.raises(ValidacionError, match="ya está cerrado"):
        await gestion.cerrar_vinculo(mundo.db, actor, v.id, CerrarVinculoIn(motivo="Otra vez"))
    with pytest.raises(DBAPIError, match="forma parte del historial"):
        async with mundo.db.begin_nested():
            await mundo.db.execute(text("UPDATE unidad_personas SET reside = true WHERE id = :id"), {"id": v.id})
    # El nuevo propietario puede ser responsable de pago (el índice único quedó libre)
    nuevo = await gestion.vincular(
        mundo.db, actor, u.id, VinculoIn(persona=_persona("Comprador", "52999888"), relacion=RelacionUnidad.PROPIETARIO)
    )
    assert nuevo.responsable_pago
    accion = await mundo.db.scalar(
        select(AuditoriaUnidad.accion).where(
            AuditoriaUnidad.entidad_id == v.id, AuditoriaUnidad.accion == AccionAuditoria.CAMBIO_ESTADO
        )
    )
    assert accion == AccionAuditoria.CAMBIO_ESTADO


async def test_membresia_del_residente_se_sincroniza(mundo: Mundo) -> None:
    residente = await mundo.usuario("RESIDENTE", "RESIDENTE")
    u1 = await _unidad(mundo, "1", "101")
    u2 = await _unidad(mundo, "1", "102")
    actor = await mundo.como(A)
    p = await gestion.crear_persona(mundo.db, actor, _persona(user_id=residente))
    v1 = await gestion.vincular(mundo.db, actor, u1.id, VinculoIn(persona_id=p.id, relacion=RelacionUnidad.PROPIETARIO))
    await gestion.vincular(
        mundo.db, actor, u2.id, VinculoIn(persona_id=p.id, relacion=RelacionUnidad.ARRENDATARIO, reside=True)
    )

    async def unidad_de_membresia() -> uuid.UUID | None:
        return await mundo.db.scalar(
            select(Membership.unit_id).where(Membership.user_id == residente, Membership.tenant_id == mundo.tenant)
        )

    assert await unidad_de_membresia() == u2.id  # donde reside tiene prioridad
    await gestion.cerrar_vinculo(
        mundo.db,
        actor,
        (await mundo.db.scalars(select(UnidadPersona).where(UnidadPersona.unidad_id == u2.id))).one().id,
        CerrarVinculoIn(motivo="Fin del arriendo"),
    )
    assert await unidad_de_membresia() == u1.id
    await gestion.cerrar_vinculo(mundo.db, actor, v1.id, CerrarVinculoIn(motivo="Venta"))
    assert await unidad_de_membresia() is None


async def test_cuenta_de_otra_copropiedad_no_se_enlaza(mundo: Mundo) -> None:
    actor = await mundo.como(A)
    with pytest.raises(ValidacionError, match="no pertenece"):
        await gestion.crear_persona(mundo.db, actor, _persona(user_id=uuid.uuid4()))


# --- Vehículos ------------------------------------------------------------------


async def test_vehiculos(mundo: Mundo) -> None:
    u1 = await _unidad(mundo, "1", "101")
    u2 = await _unidad(mundo, "1", "102")
    actor = await mundo.como(A)
    ajeno = await gestion.crear_persona(mundo.db, actor, _persona("Ajeno", "11111111"))
    with pytest.raises(ValidacionError, match="vinculado a la unidad"):
        await gestion.registrar_vehiculo(mundo.db, actor, u1.id, VehiculoIn(placa="abc-123", persona_id=ajeno.id))
    v = await gestion.registrar_vehiculo(mundo.db, actor, u1.id, VehiculoIn(placa="abc-123", marca="Mazda"))
    assert v.placa == "ABC123"
    with pytest.raises(ValidacionError, match="ABC123 ya está registrada en 1-101"):
        await gestion.registrar_vehiculo(mundo.db, actor, u2.id, VehiculoIn(placa="ABC 123"))
    await gestion.retirar_vehiculo(mundo.db, actor, v.id, "Vendió el carro")
    # Retirado el anterior, la placa se puede registrar en otra unidad
    await gestion.registrar_vehiculo(mundo.db, actor, u2.id, VehiculoIn(placa="ABC123"))


# --- Row Level Security -----------------------------------------------------------


async def test_rls_por_rol(mundo: Mundo) -> None:
    residente = await mundo.usuario("RESIDENTE", "RESIDENTE")
    await mundo.usuario("MANTENIMIENTO", "MANTENIMIENTO")
    propia = await _unidad(mundo, "1", "101")
    anexo = await _unidad(mundo, "1", "PQ-01", tipo=TipoUnidad.PARQUEADERO, unidad_principal_id=propia.id)
    ajena = await _unidad(mundo, "1", "102")
    actor = await mundo.como(A)
    yo = await gestion.crear_persona(mundo.db, actor, _persona(user_id=residente))
    await gestion.vincular(mundo.db, actor, propia.id, VinculoIn(persona_id=yo.id, relacion=RelacionUnidad.PROPIETARIO))
    familiar = await gestion.vincular(
        mundo.db, actor, propia.id, VinculoIn(persona=_persona("Hijo", None), relacion=RelacionUnidad.RESIDENTE)
    )
    vecino = await gestion.vincular(
        mundo.db,
        actor,
        ajena.id,
        VinculoIn(persona=_persona("Vecino", "33333333"), relacion=RelacionUnidad.PROPIETARIO),
    )
    await gestion.registrar_vehiculo(mundo.db, actor, propia.id, VehiculoIn(placa="AAA111"))
    await gestion.registrar_vehiculo(mundo.db, actor, ajena.id, VehiculoIn(placa="BBB222"))
    mundo.db.expunge_all()

    async def ver(modelo: type) -> set[uuid.UUID]:
        return set(await mundo.db.scalars(select(modelo.id)))

    # Residente: su unidad, el anexo, su gente y sus vehículos; nada del vecino
    await mundo.como(UserRole.RESIDENTE, "RESIDENTE")
    assert await ver(Unit) == {propia.id, anexo.id}
    assert await ver(Persona) == {yo.id, familiar.persona_id}
    assert vecino.persona_id not in await ver(Persona)
    assert {p for p in await mundo.db.scalars(select(Vehiculo.placa))} == {"AAA111"}

    # Mantenimiento: ve las unidades (ubicaciones) pero no el directorio
    await mundo.como(UserRole.MANTENIMIENTO, "MANTENIMIENTO")
    assert len(await ver(Unit)) == 3
    assert await ver(Persona) == set()

    # Recepción: directorio y vehículos, sin auditoría
    await mundo.como(UserRole.AUXILIAR)
    assert len(await ver(Persona)) == 3
    assert len(await ver(Vehiculo)) == 2
    assert await mundo.db.scalar(select(AuditoriaUnidad.id).limit(1)) is None

    # Contabilidad: directorio y auditoría, sin vehículos
    await mundo.como(UserRole.CONTABILIDAD)
    assert len(await ver(Persona)) == 3
    assert await ver(Vehiculo) == set()
    assert await mundo.db.scalar(select(AuditoriaUnidad.id).limit(1)) is not None
