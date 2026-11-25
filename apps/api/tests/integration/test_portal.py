"""Fase 1 del portal del residente: PQRS, circulares y reservas contra la base real (triggers y RLS)."""

import uuid
from datetime import time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models import CategoriaActivo, Circular, Pqrs, PqrsMensaje, Reserva
from app.models.enums import (
    CanalPqrs,
    CategoriaPqrs,
    EstadoCircular,
    EstadoPqrs,
    EstadoReserva,
    MetodoCuota,
    RelacionUnidad,
    TipoPqrs,
    UserRole,
)
from app.schemas.activos import ActivoIn
from app.schemas.cartera import ConfigIn, EmitirPeriodoIn
from app.schemas.portal import (
    CalificacionIn,
    CancelarReservaIn,
    CircularIn,
    DecisionReservaIn,
    GestionPqrsIn,
    MensajeIn,
    NovedadDesdePqrsIn,
    PqrsIn,
    ReabrirIn,
    ReglasZonaIn,
    ReservaPortalIn,
    RespuestaIn,
)
from app.schemas.recaudos import ZonaCreate
from app.schemas.unidades import PersonaIn, UnidadIn, VinculoIn
from app.services.activos import activos
from app.services.cartera import comun as cartera_comun
from app.services.cartera import facturacion
from app.services.comun import PermisoDenegado, ValidacionError, hoy_bogota
from app.services.portal import circulares, pqrs, reservas
from app.services.portal import dominio as d
from app.services.recaudos import catalogos
from app.services.unidades import gestion
from tests.integration.conftest import Mundo

A = UserRole.ADMIN
RES = UserRole.RESIDENTE
HOY = hoy_bogota()


@pytest.fixture
async def portal(mundo: Mundo) -> dict[str, uuid.UUID]:
    """Torre 1: 101 (residente «Ana») y 102 (residente «Beto»); torre 2: 201 sin cuenta. Una zona social."""
    for clave in ("ANA", "BETO"):
        await mundo.usuario(clave, "RESIDENTE")
    admin = await mundo.como(A)
    ids: dict[str, uuid.UUID] = {}
    for torre, numero, quien in (("1", "101", "ANA"), ("1", "102", "BETO"), ("2", "201", None)):
        u = await gestion.crear_unidad(
            mundo.db, admin, UnidadIn(tower=torre, number=numero, coefficient=Decimal("33.3"))
        )
        ids[numero] = u.id
        persona = PersonaIn(
            nombre_completo=f"Propietario {numero}",
            email=f"p{numero}@correo.demo",
            user_id=mundo.usuarios[quien] if quien else None,
        )
        await gestion.vincular(
            mundo.db, admin, u.id, VinculoIn(persona=persona, relacion=RelacionUnidad.PROPIETARIO, reside=True)
        )
    z = await catalogos.crear_zona(mundo.db, admin, ZonaCreate(nombre="Salón social", tarifa_alquiler=Decimal(150000)))
    await reservas.configurar_zona(mundo.db, admin, z.id, ReglasZonaIn(capacidad=40, requiere_paz_y_salvo=True))
    ids["zona"] = z.id
    return ids


async def _radicar(m: Mundo, quien: str, unidad: uuid.UUID | None = None, **extra: object) -> Pqrs:
    actor = await m.como(RES, quien)
    datos = {
        "tipo": TipoPqrs.QUEJA,
        "categoria": CategoriaPqrs.CONVIVENCIA,
        "asunto": "Ruido en la noche",
        "descripcion": "Música a alto volumen después de las 11 p. m.",
        "unidad_id": unidad,
        **extra,
    }
    return await pqrs.radicar(m.db, actor, PqrsIn(**datos))  # type: ignore[arg-type]


# --- PQRS -------------------------------------------------------------------------------


async def test_radicar_y_flujo_completo(mundo: Mundo, portal: dict[str, uuid.UUID]) -> None:
    p = await _radicar(mundo, "ANA", portal["101"])
    assert p.estado == EstadoPqrs.RADICADA and p.consecutivo >= 1
    assert p.fecha_limite == d.sumar_dias_habiles(HOY, 15)
    assert p.solicitante_nombre == "Ana" and p.canal == CanalPqrs.PORTAL

    aux = await mundo.como(UserRole.AUXILIAR)
    await pqrs.comentar(mundo.db, aux, p.id, MensajeIn(texto="Ya hablamos con el vecino", interno=True))
    await pqrs.comentar(mundo.db, aux, p.id, MensajeIn(texto="Estamos revisando su caso"))
    await mundo.db.refresh(p)
    assert p.estado == EstadoPqrs.EN_TRAMITE  # el primer mensaje público la pone en trámite
    p = await pqrs.responder(mundo.db, aux, p.id, RespuestaIn(texto="Se envió un llamado de atención por escrito"))
    assert p.estado == EstadoPqrs.RESPONDIDA and p.respondida_at is not None

    # La residente no ve la nota interna
    ana = await mundo.como(RES, "ANA")
    mensajes = list(await mundo.db.scalars(select(PqrsMensaje.texto).where(PqrsMensaje.pqrs_id == p.id)))
    assert "Ya hablamos con el vecino" not in mensajes and len(mensajes) == 2
    # Reabre (no quedó satisfecha) y luego califica cuando le responden de nuevo
    p = await pqrs.reabrir(mundo.db, ana, p.id, ReabrirIn(texto="El ruido continuó el sábado"))
    assert p.estado == EstadoPqrs.EN_TRAMITE
    aux = await mundo.como(UserRole.AUXILIAR)
    await pqrs.responder(
        mundo.db, aux, p.id, RespuestaIn(texto="Se impuso la multa prevista en el manual de convivencia")
    )
    ana = await mundo.como(RES, "ANA")
    p = await pqrs.calificar(mundo.db, ana, p.id, CalificacionIn(calificacion=4))
    assert p.estado == EstadoPqrs.CERRADA and p.cerrada_at is not None
    with pytest.raises(ValidacionError, match="está cerrada"):
        await pqrs.comentar(mundo.db, ana, p.id, MensajeIn(texto="otra cosa"))


async def test_privacidad_y_permisos(mundo: Mundo, portal: dict[str, uuid.UUID]) -> None:
    p = await _radicar(mundo, "ANA", portal["101"])
    mundo.db.expunge_all()  # sin caché: la consulta pasa por la RLS, como en una petición nueva
    beto = await mundo.como(RES, "BETO")
    assert await mundo.db.get(Pqrs, p.id) is None  # Beto no ve la queja de Ana
    with pytest.raises(Exception, match="no encontrada"):
        await pqrs.comentar(mundo.db, beto, p.id, MensajeIn(texto="hola"))
    # Ana no puede radicar a nombre de otra unidad ni cambiar el canal
    with pytest.raises(Exception, match="no encontrada"):
        await _radicar(mundo, "ANA", portal["102"])
    with pytest.raises(PermisoDenegado):
        await _radicar(mundo, "ANA", canal=CanalPqrs.PRESENCIAL)
    ana = await mundo.como(RES, "ANA")
    with pytest.raises(PermisoDenegado):
        await pqrs.comentar(mundo.db, ana, p.id, MensajeIn(texto="nota", interno=True))
    # Lo radicado no se modifica (trigger) y no se salta la respuesta
    with pytest.raises(DBAPIError, match="no se modifica"):
        async with mundo.db.begin_nested():
            await mundo.db.execute(text("UPDATE pqrs SET asunto = 'otro asunto' WHERE id = :id"), {"id": p.id})
    admin = await mundo.como(A)
    with pytest.raises(ValidacionError, match="No se puede pasar"):
        await pqrs.gestionar(mundo.db, admin, p.id, GestionPqrsIn(estado=EstadoPqrs.CERRADA))


async def test_radicada_por_recepcion_y_asignada(mundo: Mundo, portal: dict[str, uuid.UUID]) -> None:
    tecnico = await mundo.usuario("TECNICO", "MANTENIMIENTO")
    aux = await mundo.como(UserRole.AUXILIAR)
    p = await pqrs.radicar(
        mundo.db,
        aux,
        PqrsIn(
            tipo=TipoPqrs.RECLAMO,
            categoria=CategoriaPqrs.MANTENIMIENTO,
            asunto="Filtración en el techo",
            descripcion="Mancha de humedad en la habitación principal",
            unidad_id=portal["201"],
            canal=CanalPqrs.PRESENCIAL,
            solicitante_nombre="Propietario 201",
        ),
    )
    assert p.solicitante_nombre == "Propietario 201"
    p = await pqrs.gestionar(mundo.db, aux, p.id, GestionPqrsIn(asignado_a_id=tecnico))
    assert p.asignado_a_id == tecnico and p.estado == EstadoPqrs.EN_TRAMITE
    tec = await mundo.como(UserRole.MANTENIMIENTO, "TECNICO")
    assert await mundo.db.get(Pqrs, p.id) is not None  # el técnico ve la que tiene asignada

    # Se convierte en novedad de mantenimiento
    admin = await mundo.como(A)
    await mundo.db.execute(text("SELECT seed_categorias_activos(:t)"), {"t": mundo.tenant})
    cat = (
        await mundo.db.scalars(select(CategoriaActivo.id).where(CategoriaActivo.codigo == "ESTRUCTURA_ENVOLVENTE"))
    ).first()
    if cat is None:
        cat = (await mundo.db.scalars(select(CategoriaActivo.id))).first()
    a = await activos.crear_activo(
        mundo.db, admin, ActivoIn(nombre="Cubierta torre 2", categoria_id=cat, ubicacion="Torre 2")
    )
    p = await pqrs.convertir_en_novedad(mundo.db, admin, p.id, NovedadDesdePqrsIn(activo_id=a.id, prioridad="ALTA"))
    assert p.novedad_id is not None
    del tec


# --- Circulares ---------------------------------------------------------------------------


async def test_circulares(mundo: Mundo, portal: dict[str, uuid.UUID]) -> None:
    admin = await mundo.como(A)
    general = await circulares.crear(
        mundo.db,
        admin,
        CircularIn(
            titulo="Asamblea ordinaria 2027",
            cuerpo="Se convoca a la asamblea ordinaria el 15 de marzo.",
            importante=True,
        ),
    )
    torre2 = await circulares.crear(
        mundo.db,
        admin,
        CircularIn(
            titulo="Corte de agua torre 2",
            cuerpo="El jueves no habrá agua de 8 a 12 en la torre 2.",
            torres=["Torre 2"],
        ),
    )
    assert torre2.torres == ["2"]
    with pytest.raises(ValidacionError, match="torre 9"):
        await circulares.crear(
            mundo.db,
            admin,
            CircularIn(titulo="Torre inexistente", cuerpo="Esta torre no existe en el conjunto", torres=["9"]),
        )

    # Los residentes no ven borradores
    mundo.db.expunge_all()
    ana = await mundo.como(RES, "ANA")
    assert await mundo.db.get(Circular, general.id) is None
    admin = await mundo.como(A)
    general = await circulares.publicar(mundo.db, admin, general.id)
    torre2 = await circulares.publicar(mundo.db, admin, torre2.id)
    assert general.estado == EstadoCircular.PUBLICADA and general.consecutivo and general.publicada_at
    with pytest.raises(DBAPIError, match="no se edita"):
        async with mundo.db.begin_nested():
            await mundo.db.execute(text("UPDATE circulares SET titulo = 'Cambiado' WHERE id = :id"), {"id": general.id})

    # Destinatarios: correo de las personas del directorio de la torre (también sin cuenta)
    correos_t2 = {x.email for x in await circulares.destinatarios(mundo.db, torre2)}
    assert correos_t2 == {"p201@correo.demo"}
    # A Ana (torre 1) le aplica la general, no la de la torre 2
    ana = await mundo.como(RES, "ANA")
    torres = await circulares.torres_del_usuario(mundo.db, ana)
    assert torres == {"1"} and circulares.le_aplica(general, torres) and not circulares.le_aplica(torre2, torres)
    await circulares.marcar_leida(mundo.db, ana, general.id)
    await circulares.marcar_leida(mundo.db, ana, general.id)  # idempotente
    admin = await mundo.como(A)
    leidas, total = await circulares.estadisticas_lectura(mundo.db, admin, general)
    assert (leidas, total) == (1, 2)  # Ana leyó; Beto no


# --- Reservas ------------------------------------------------------------------------------


async def test_reserva_desde_el_portal(mundo: Mundo, portal: dict[str, uuid.UUID]) -> None:
    fecha = HOY + timedelta(days=10)
    ana = await mundo.como(RES, "ANA")
    r = await reservas.solicitar(
        mundo.db,
        ana,
        ReservaPortalIn(
            zona_id=portal["zona"],
            unidad_id=portal["101"],
            fecha_evento=fecha,
            hora_inicio=time(14),
            hora_fin=time(20),
            numero_asistentes=30,
        ),
    )
    assert r.estado == EstadoReserva.SOLICITADA and r.solicitada_en_portal

    # Beto ve la franja ocupada pero no sabe de quién, y no puede reservar encima
    mundo.db.expunge_all()
    beto = await mundo.como(RES, "BETO")
    ocupado = await reservas.disponibilidad(mundo.db, beto, portal["zona"], fecha, fecha)
    assert len(ocupado) == 1 and not ocupado[0].propia
    assert await mundo.db.get(Reserva, r.id) is None
    with pytest.raises(ValidacionError, match="ya está reservada"):
        await reservas.solicitar(
            mundo.db,
            beto,
            ReservaPortalIn(
                zona_id=portal["zona"],
                unidad_id=portal["102"],
                fecha_evento=fecha,
                hora_inicio=time(18),
                hora_fin=time(22),
            ),
        )
    with pytest.raises(ValidacionError, match="capacidad máxima"):
        await reservas.solicitar(
            mundo.db,
            beto,
            ReservaPortalIn(
                zona_id=portal["zona"],
                unidad_id=portal["102"],
                fecha_evento=fecha,
                hora_inicio=time(8),
                hora_fin=time(12),
                numero_asistentes=80,
            ),
        )

    # La administración aprueba; Ana cancela; el portal no deja reabrirla
    aux = await mundo.como(UserRole.AUXILIAR)
    r = await reservas.decidir(mundo.db, aux, r.id, DecisionReservaIn(aprobar=True))
    assert r.estado == EstadoReserva.CONFIRMADA
    ana = await mundo.como(RES, "ANA")
    r = await reservas.cancelar(mundo.db, ana, r.id, CancelarReservaIn(motivo="Cambiamos de planes"))
    assert r.estado == EstadoReserva.CANCELADA
    with pytest.raises(DBAPIError, match="solo puede cancelar"):
        async with mundo.db.begin_nested():
            await mundo.db.execute(text("UPDATE reservas SET estado = 'CONFIRMADA' WHERE id = :id"), {"id": r.id})


async def test_reserva_exige_paz_y_salvo(mundo: Mundo, portal: dict[str, uuid.UUID]) -> None:
    await mundo.db.execute(text("SELECT seed_conceptos_cartera(:t)"), {"t": mundo.tenant})
    admin = await mundo.como(A)
    await cartera_comun.guardar_config(
        mundo.db, admin, ConfigIn(metodo=MetodoCuota.COEFICIENTE, presupuesto_mensual=Decimal(1000000))
    )
    pasado = (HOY.replace(day=1) - timedelta(days=1)).replace(day=1)
    await facturacion.emitir(mundo.db, admin, EmitirPeriodoIn(anio=pasado.year, mes=pasado.month, fecha_emision=pasado))
    ana = await mundo.como(RES, "ANA")
    with pytest.raises(ValidacionError, match="debe estar al día"):
        await reservas.solicitar(
            mundo.db,
            ana,
            ReservaPortalIn(
                zona_id=portal["zona"],
                unidad_id=portal["101"],
                fecha_evento=HOY + timedelta(days=5),
                hora_inicio=time(10),
                hora_fin=time(12),
            ),
        )
    # Sin ese requisito, y con aprobación automática, queda confirmada de una vez
    admin = await mundo.como(A)
    await reservas.configurar_zona(
        mundo.db, admin, portal["zona"], ReglasZonaIn(requiere_paz_y_salvo=False, requiere_aprobacion=False)
    )
    ana = await mundo.como(RES, "ANA")
    r = await reservas.solicitar(
        mundo.db,
        ana,
        ReservaPortalIn(
            zona_id=portal["zona"],
            unidad_id=portal["101"],
            fecha_evento=HOY + timedelta(days=5),
            hora_inicio=time(10),
            hora_fin=time(12),
        ),
    )
    assert r.estado == EstadoReserva.CONFIRMADA
