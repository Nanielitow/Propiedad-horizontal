"""Fase 1 del módulo de activos: servicios, triggers, RLS y auditoría contra la base real."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models import (
    ActividadProgramada,
    Activo,
    AuditoriaActivo,
    CategoriaActivo,
    PlanPreventivo,
    RecomendacionTecnica,
)
from app.models.enums import (
    BaseCalculo,
    EstadoActividad,
    EstadoActivo,
    EstadoNovedad,
    EstadoRecomendacion,
    Periodicidad,
    PrioridadNovedad,
    TipoMantenimiento,
    UserRole,
)
from app.schemas.activos import (
    ActivoIn,
    ActivoUpdate,
    BajaIn,
    MantenimientoIn,
    NovedadAvance,
    NovedadIn,
    PlanIn,
    RecomendacionNueva,
    RecomendacionUpdate,
    ReprogramacionIn,
)
from app.services.activos import activos, mantenimientos, novedades, planes, recomendaciones, semaforo
from app.services.comun import TZ, PermisoDenegado, TransicionInvalida, ValidacionError
from tests.integration.conftest import AHORA, Mundo

pytestmark = pytest.mark.integration

HOY = AHORA.astimezone(TZ).date()
E = EstadoNovedad


@pytest.fixture
async def m(mundo: Mundo) -> Mundo:
    await mundo.usuario("MANTENIMIENTO", "MANTENIMIENTO")
    await set_seed(mundo)
    return mundo


async def set_seed(mundo: Mundo) -> None:
    from app.db.rls import set_rls_context

    await set_rls_context(mundo.db, tenant_id=mundo.tenant, role="SYSTEM")
    await mundo.db.execute(text("SELECT seed_categorias_activos(:t)"), {"t": mundo.tenant})


async def categoria(m: Mundo, codigo: str = "ELECTROMECANICOS") -> uuid.UUID:
    return (await m.db.scalars(select(CategoriaActivo.id).where(CategoriaActivo.codigo == codigo))).one()


async def nuevo_activo(m: Mundo, nombre: str = "Motobomba principal") -> Activo:
    admin = await m.como(UserRole.ADMIN)
    return await activos.crear_activo(
        m.db,
        admin,
        ActivoIn(
            nombre=nombre,
            categoria_id=await categoria(m),
            subtipo="Motobomba",
            ubicacion="Torre 1 · Sótano 2",
            especificaciones={"Potencia": "15 HP", "Caudal": "120 L/min"},
            fecha_instalacion=HOY - timedelta(days=3650),
            vida_util_anios=20,
        ),
    )


async def plan_aprobado(m: Mundo, activo: Activo, **cambios: object) -> tuple[PlanPreventivo, int]:
    admin = await m.como(UserRole.ADMIN)
    datos = {
        "activo_id": activo.id,
        "nombre": "Mantenimiento mensual",
        "periodicidad": Periodicidad.MENSUAL,
        "fecha_inicio": HOY,
    }
    plan = await planes.crear_plan(m.db, admin, PlanIn(**(datos | cambios)))
    return await planes.aprobar_plan(m.db, admin, plan.id, hoy=HOY)


def preventivo(activo: Activo, actividad_id: uuid.UUID | None, **extra: object) -> MantenimientoIn:
    datos = {
        "activo_id": activo.id,
        "tipo": TipoMantenimiento.PREVENTIVO,
        "fecha_ejecucion": HOY,
        "nombre_tecnico": "Pedro Ramírez",
        "actividades_realizadas": "Revisión de sellos, rodamientos y presión",
        "estado_post_intervencion": EstadoActivo.OPERATIVO,
        "actividad_id": actividad_id,
    }
    return MantenimientoIn(**(datos | extra))


async def falla(m: Mundo, sql: str, params: dict[str, object], coincide: str) -> None:
    with pytest.raises(DBAPIError, match=coincide):
        async with m.db.begin_nested():
            await m.db.execute(text(sql), params)


# --- Activos -------------------------------------------------------------------------


async def test_alta_de_activo_con_codigo_qr_y_auditoria(m: Mundo) -> None:
    a = await nuevo_activo(m)
    b = await nuevo_activo(m, "Motobomba auxiliar")
    assert (a.codigo_interno, b.codigo_interno) == ("ACT-001", "ACT-002")
    assert len(a.qr_token) == 32 and a.qr_token != b.qr_token

    tecnico = await m.como(UserRole.MANTENIMIENTO)
    with pytest.raises(PermisoDenegado):
        await activos.crear_activo(m.db, tecnico, ActivoIn(nombre="X1", categoria_id=a.categoria_id, ubicacion="Lobby"))
    assert (await activos.por_qr(m.db, tecnico, a.qr_token)).id == a.id  # el técnico consulta por QR

    auxiliar = await m.como(UserRole.AUXILIAR)
    await activos.editar_activo(
        m.db, auxiliar, a.id, ActivoUpdate(marca="Pedrollo", motivo="Placa del equipo leída en sitio")
    )
    admin = await m.como(UserRole.ADMIN)
    viejo = a.qr_token
    await activos.regenerar_qr(m.db, admin, a.id)
    assert a.qr_token != viejo

    eventos = (
        await m.db.scalars(
            select(AuditoriaActivo).where(AuditoriaActivo.entidad_id == a.id).order_by(AuditoriaActivo.id)
        )
    ).all()
    assert [e.accion.value for e in eventos] == ["CREACION", "EDICION", "EDICION"]
    assert eventos[1].valores_nuevos == {"marca": "Pedrollo"}
    assert eventos[1].motivo == "Placa del equipo leída en sitio"


async def test_baja_reemplaza_al_borrado(m: Mundo) -> None:
    a = await nuevo_activo(m)
    await falla(m, "DELETE FROM activos WHERE id = :id", {"id": a.id}, "permission denied")
    auxiliar = await m.como(UserRole.AUXILIAR)
    with pytest.raises(PermisoDenegado):
        await activos.dar_de_baja(m.db, auxiliar, a.id, BajaIn(motivo="Equipo reemplazado por uno nuevo"))
    admin = await m.como(UserRole.ADMIN)
    await activos.dar_de_baja(m.db, admin, a.id, BajaIn(motivo="Equipo reemplazado por uno nuevo"))
    assert a.estado == EstadoActivo.DADO_DE_BAJA
    with pytest.raises(ValidacionError, match="dado de baja"):
        await activos.editar_activo(m.db, admin, a.id, ActivoUpdate(ubicacion="Otra", motivo="prueba de edición"))
    await falla(m, "UPDATE activos SET ubicacion = 'x' WHERE id = :id", {"id": a.id}, "dado de baja")


async def test_consejo_y_residentes_no_ven_el_detalle(m: Mundo) -> None:
    await nuevo_activo(m)
    from app.db.rls import set_rls_context

    for rol in ("CONSEJO", "RESIDENTE"):
        await set_rls_context(m.db, tenant_id=m.tenant, role=rol)
        assert await m.db.scalar(text("SELECT count(*) FROM activos")) == 0


# --- Plan, actividades y semáforo -----------------------------------------------------


async def test_aprobar_plan_programa_doce_meses_sin_duplicar(m: Mundo) -> None:
    a = await nuevo_activo(m)
    auxiliar = await m.como(UserRole.AUXILIAR)
    propuesto = await planes.crear_plan(
        m.db,
        auxiliar,
        PlanIn(activo_id=a.id, nombre="Revisión mensual", periodicidad=Periodicidad.MENSUAL, fecha_inicio=HOY),
    )
    with pytest.raises(PermisoDenegado):
        await planes.aprobar_plan(m.db, auxiliar, propuesto.id)

    admin = await m.como(UserRole.ADMIN)
    _, creadas = await planes.aprobar_plan(m.db, admin, propuesto.id, hoy=HOY)
    assert creadas == 13  # hoy y los 12 meses siguientes, ambos extremos incluidos
    assert await planes.extender_programacion(m.db, HOY) == 0  # idempotente


async def test_reprogramar_deja_rastro_y_sin_registro_es_imposible(m: Mundo) -> None:
    a = await nuevo_activo(m)
    plan, _ = await plan_aprobado(m, a)
    act = (
        await m.db.scalars(
            select(ActividadProgramada)
            .where(ActividadProgramada.plan_id == plan.id)
            .order_by(ActividadProgramada.fecha_programada)
        )
    ).first()
    assert act is not None
    await falla(
        m,
        "UPDATE actividades_programadas SET fecha_programada = fecha_programada + 3 WHERE id = :id",
        {"id": act.id},
        "registre la reprogramación",
    )
    auxiliar = await m.como(UserRole.AUXILIAR)
    with pytest.raises(ValidacionError, match="pasada"):
        await planes.reprogramar(
            m.db, auxiliar, act.id, ReprogramacionIn(nueva_fecha=HOY - timedelta(days=1), motivo="Prueba al pasado")
        )
    original = act.fecha_programada
    await planes.reprogramar(
        m.db,
        auxiliar,
        act.id,
        ReprogramacionIn(nueva_fecha=original + timedelta(days=4), motivo="El contratista pidió cambio de día"),
    )
    assert (act.fecha_programada, act.fecha_original) == (original + timedelta(days=4), original)
    historial = (
        await m.db.execute(
            text("SELECT fecha_anterior, nueva_fecha, motivo FROM reprogramaciones WHERE actividad_id = :id"),
            {"id": act.id},
        )
    ).one()
    assert historial == (original, original + timedelta(days=4), "El contratista pidió cambio de día")


async def test_semaforo_calculado_al_consultar(m: Mundo) -> None:
    a = await nuevo_activo(m)
    plan, _ = await plan_aprobado(m, a, periodicidad=Periodicidad.SEMANAL)  # hoy, +7, +14, +21...
    from app.db.rls import set_rls_context

    await set_rls_context(m.db, tenant_id=m.tenant, role="SYSTEM")  # una actividad vencida (generada en el pasado)
    await m.db.execute(
        text(
            "INSERT INTO actividades_programadas (tenant_id, plan_id, activo_id, fecha_programada, fecha_original)"
            " VALUES (:t, :p, :a, :f, :f)"
        ),
        {"t": m.tenant, "p": plan.id, "a": a.id, "f": HOY - timedelta(days=2)},
    )
    await m.como(UserRole.MANTENIMIENTO)
    colores = {x.dias_restantes: x.color for x in await semaforo.actividades(m.db, a.id)}
    assert colores[-2] == "ROJO"
    assert colores[0] == colores[7] == colores[14] == "AMARILLO"
    assert colores[21] == "VERDE"
    assert (await semaforo.por_activo(m.db))[a.id] == "ROJO"


# --- Mantenimientos ------------------------------------------------------------------


async def test_ejecutar_preventivo_cumple_la_actividad_y_actualiza_el_activo(m: Mundo) -> None:
    a = await nuevo_activo(m)
    plan, _ = await plan_aprobado(m, a)
    act = (
        await m.db.scalars(
            select(ActividadProgramada)
            .where(ActividadProgramada.plan_id == plan.id)
            .order_by(ActividadProgramada.fecha_programada)
        )
    ).first()
    assert act is not None

    tecnico = await m.como(UserRole.MANTENIMIENTO)
    mto, recs = await mantenimientos.registrar(
        m.db,
        tecnico,
        preventivo(
            a,
            act.id,
            estado_post_intervencion=EstadoActivo.OPERATIVO_CON_OBSERVACIONES,
            costo_mano_obra=Decimal(180000),
            costo_repuestos=Decimal(45000),
            recomendaciones=[
                RecomendacionNueva(descripcion="Cambiar el sello mecánico", costo_estimado=Decimal(350000))
            ],
        ),
    )
    assert (mto.codigo, mto.costo_total) == ("MTO-0001", Decimal("225000.00"))
    await m.db.refresh(act)
    assert act.estado == EstadoActividad.EJECUTADA
    assert a.estado == EstadoActivo.OPERATIVO_CON_OBSERVACIONES  # lo actualizó el trigger
    assert recs[0].mantenimiento_origen_id == mto.id

    # El historial no se edita ni se borra (ni siquiera la administración)
    await m.como(UserRole.ADMIN)
    await falla(
        m, "UPDATE mantenimientos_ejecutados SET costo_repuestos = 0 WHERE id = :id", {"id": mto.id}, "no se edita"
    )
    await falla(m, "DELETE FROM mantenimientos_ejecutados WHERE id = :id", {"id": mto.id}, "permission denied")
    with pytest.raises(TransicionInvalida):
        await mantenimientos.registrar(m.db, tecnico, preventivo(a, act.id))  # la actividad ya se cumplió

    auxiliar = await m.como(UserRole.AUXILIAR)
    with pytest.raises(PermisoDenegado):
        await mantenimientos.anular(m.db, auxiliar, mto.id, "Se registró en el activo equivocado")
    admin = await m.como(UserRole.ADMIN)
    await mantenimientos.anular(m.db, admin, mto.id, "Se registró en el activo equivocado")
    await m.db.refresh(act)
    assert act.estado == EstadoActividad.PROGRAMADA  # vuelve a quedar pendiente


async def test_plan_desde_ultima_ejecucion_programa_la_siguiente_fecha(m: Mundo) -> None:
    a = await nuevo_activo(m)
    plan, creadas = await plan_aprobado(
        m, a, base_calculo=BaseCalculo.DESDE_ULTIMA_EJECUCION, periodicidad=Periodicidad.TRIMESTRAL
    )
    assert creadas == 1
    [act] = (await m.db.scalars(select(ActividadProgramada).where(ActividadProgramada.plan_id == plan.id))).all()

    tecnico = await m.como(UserRole.MANTENIMIENTO)
    ejecucion = HOY - timedelta(days=5)
    mto, _ = await mantenimientos.registrar(m.db, tecnico, preventivo(a, act.id, fecha_ejecucion=ejecucion))
    pendientes = (
        await m.db.scalars(
            select(ActividadProgramada.fecha_programada).where(
                ActividadProgramada.plan_id == plan.id, ActividadProgramada.estado == EstadoActividad.PROGRAMADA
            )
        )
    ).all()
    from app.services.activos.dominio import siguiente_fecha

    assert pendientes == [siguiente_fecha(ejecucion, Periodicidad.TRIMESTRAL)]  # cuenta desde la ejecución real

    admin = await m.como(UserRole.ADMIN)
    await mantenimientos.anular(m.db, admin, mto.id, "Registro duplicado por el técnico")
    estados = dict(
        (
            await m.db.execute(
                text("SELECT fecha_programada, estado::text FROM actividades_programadas WHERE plan_id = :p"),
                {"p": plan.id},
            )
        ).all()
    )
    assert estados[act.fecha_programada] == "PROGRAMADA"
    assert estados[pendientes[0]] == "CANCELADA"  # la siguiente fecha que generó ya no aplica


# --- Novedades y recomendaciones -----------------------------------------------------


async def test_flujo_de_novedad_hasta_el_cierre(m: Mundo) -> None:
    a = await nuevo_activo(m)
    tecnico = await m.como(UserRole.MANTENIMIENTO)
    nov = await novedades.reportar(
        m.db,
        tecnico,
        NovedadIn(activo_id=a.id, descripcion="Ruido fuerte y vibración al arrancar", prioridad=PrioridadNovedad.ALTA),
    )
    assert (nov.codigo, nov.estado) == ("NOV-0001", E.REPORTADA)
    with pytest.raises(PermisoDenegado, match="asignadas"):
        await novedades.avanzar(m.db, tecnico, nov.id, NovedadAvance(estado=E.EN_GESTION))

    auxiliar = await m.como(UserRole.AUXILIAR)
    await novedades.avanzar(
        m.db, auxiliar, nov.id, NovedadAvance(estado=E.EN_GESTION, asignado_a_id=m.usuarios["MANTENIMIENTO"])
    )
    assert nov.fecha_atencion is not None  # mide el tiempo de respuesta
    with pytest.raises(TransicionInvalida):
        await novedades.avanzar(m.db, auxiliar, nov.id, NovedadAvance(estado=E.CERRADA))

    tecnico = await m.como(UserRole.MANTENIMIENTO)
    await novedades.avanzar(
        m.db, tecnico, nov.id, NovedadAvance(estado=E.EN_EJECUCION, diagnostico="Rodamiento desgastado")
    )
    correctivo, _ = await mantenimientos.registrar(
        m.db,
        tecnico,
        preventivo(
            a, None, tipo=TipoMantenimiento.CORRECTIVO, novedad_id=nov.id, actividades_realizadas="Cambio de rodamiento"
        ),
    )
    auxiliar = await m.como(UserRole.AUXILIAR)
    with pytest.raises(PermisoDenegado):
        await novedades.avanzar(m.db, auxiliar, nov.id, NovedadAvance(estado=E.CERRADA))
    admin = await m.como(UserRole.ADMIN)
    await novedades.avanzar(m.db, admin, nov.id, NovedadAvance(estado=E.CERRADA))  # el correctivo vinculado basta
    assert nov.estado == E.CERRADA and correctivo.novedad_id == nov.id
    await falla(m, "UPDATE novedades SET diagnostico = 'x' WHERE id = :id", {"id": nov.id}, "ya está cerrada")


async def test_cierre_exige_solucion_y_descarte_exige_motivo(m: Mundo) -> None:
    a = await nuevo_activo(m)
    admin = await m.como(UserRole.ADMIN)
    nov = await novedades.reportar(m.db, admin, NovedadIn(activo_id=a.id, descripcion="Fuga en la tubería de succión"))
    for estado in (E.EN_GESTION, E.EN_EJECUCION):
        await novedades.avanzar(m.db, admin, nov.id, NovedadAvance(estado=estado))
    with pytest.raises(ValidacionError, match="registre la solución"):
        await novedades.avanzar(m.db, admin, nov.id, NovedadAvance(estado=E.CERRADA))
    await novedades.avanzar(
        m.db, admin, nov.id, NovedadAvance(estado=E.CERRADA, solucion_implementada="Se cambió el empaque")
    )

    otra = await novedades.reportar(m.db, admin, NovedadIn(activo_id=a.id, descripcion="Reporte duplicado de la fuga"))
    with pytest.raises(ValidacionError, match="motivo"):
        await novedades.avanzar(m.db, admin, otra.id, NovedadAvance(estado=E.DESCARTADA))
    await novedades.avanzar(
        m.db, admin, otra.id, NovedadAvance(estado=E.DESCARTADA, motivo_descarte="Duplicado de la novedad anterior")
    )
    assert otra.estado == E.DESCARTADA


async def test_novedad_critica_pone_el_activo_fuera_de_servicio(m: Mundo) -> None:
    a = await nuevo_activo(m)
    auxiliar = await m.como(UserRole.AUXILIAR)
    await novedades.reportar(
        m.db,
        auxiliar,
        NovedadIn(
            activo_id=a.id,
            descripcion="Motor quemado",
            prioridad=PrioridadNovedad.CRITICA,
            poner_fuera_de_servicio=True,
        ),
    )
    assert a.estado == EstadoActivo.FUERA_DE_SERVICIO


async def test_recomendacion_la_actualiza_su_responsable_y_descartar_exige_justificacion(m: Mundo) -> None:
    a = await nuevo_activo(m)
    tecnico = await m.como(UserRole.MANTENIMIENTO)
    _, [rec] = await mantenimientos.registrar(
        m.db,
        tecnico,
        preventivo(
            a,
            None,
            tipo=TipoMantenimiento.INSPECCION_TECNICA,
            recomendaciones=[RecomendacionNueva(descripcion="Pintar la base del equipo")],
        ),
    )
    with pytest.raises(PermisoDenegado):  # aún no es su responsable
        await recomendaciones.actualizar(
            m.db, tecnico, rec.id, RecomendacionUpdate(estado=EstadoRecomendacion.EN_PROCESO)
        )
    admin = await m.como(UserRole.ADMIN)
    await recomendaciones.actualizar(
        m.db, admin, rec.id, RecomendacionUpdate(responsable_id=m.usuarios["MANTENIMIENTO"])
    )
    tecnico = await m.como(UserRole.MANTENIMIENTO)
    await recomendaciones.actualizar(m.db, tecnico, rec.id, RecomendacionUpdate(estado=EstadoRecomendacion.EN_PROCESO))
    with pytest.raises(PermisoDenegado):
        await recomendaciones.actualizar(m.db, tecnico, rec.id, RecomendacionUpdate(costo_estimado=Decimal(1)))

    admin = await m.como(UserRole.ADMIN)
    with pytest.raises(ValidacionError, match="justificación"):
        await recomendaciones.actualizar(
            m.db, admin, rec.id, RecomendacionUpdate(estado=EstadoRecomendacion.DESCARTADA_CON_JUSTIFICACION)
        )
    await recomendaciones.actualizar(
        m.db,
        admin,
        rec.id,
        RecomendacionUpdate(
            estado=EstadoRecomendacion.DESCARTADA_CON_JUSTIFICACION,
            justificacion_descarte="Se reemplazará el equipo el próximo año",
        ),
    )
    assert (await m.db.get(RecomendacionTecnica, rec.id)).estado == EstadoRecomendacion.DESCARTADA_CON_JUSTIFICACION  # type: ignore[union-attr]


async def test_auditoria_no_se_escribe_a_mano(m: Mundo) -> None:
    a = await nuevo_activo(m)
    await falla(
        m,
        "INSERT INTO auditoria_activos (tenant_id, entidad, entidad_id, accion) VALUES (:t, 'activo', :id, 'EDICION')",
        {"t": m.tenant, "id": a.id},
        "permission denied",
    )
    await falla(m, "DELETE FROM auditoria_activos WHERE entidad_id = :id", {"id": a.id}, "permission denied")


async def test_la_base_impide_cerrar_sin_solucion_aunque_el_codigo_falle(m: Mundo) -> None:
    a = await nuevo_activo(m)
    admin = await m.como(UserRole.ADMIN)
    nov = await novedades.reportar(m.db, admin, NovedadIn(activo_id=a.id, descripcion="Filtración en la cubierta"))
    for estado in (E.EN_GESTION, E.EN_EJECUCION):
        await novedades.avanzar(m.db, admin, nov.id, NovedadAvance(estado=estado))
    await falla(
        m,
        "UPDATE novedades SET estado = 'CERRADA', cerrada_por_id = :u, cerrada_at = now() WHERE id = :id",
        {"id": nov.id, "u": m.usuarios["ADMIN"]},
        "registre la solución",
    )
    await falla(
        m,
        "UPDATE novedades SET estado = 'REPORTADA' WHERE id = :id",
        {"id": nov.id},
        "Transición de estado no permitida",
    )
