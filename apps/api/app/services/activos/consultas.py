"""Consultas de lectura del módulo de activos: buscador, hoja de vida, calendario,
historial, novedades y recomendaciones.

Todo pasa por RLS (cada rol ve lo suyo). Los nombres de personas, contratistas y
categorías se cargan una vez por petición (son pocos por copropiedad). Los costos
se devuelven en null a quien no debe verlos.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ActividadProgramada,
    Activo,
    ActivoDocumento,
    AuditoriaActivo,
    CategoriaActivo,
    Contratista,
    Document,
    Evidencia,
    LecturaUso,
    MantenimientoEjecutado,
    Membership,
    Novedad,
    PlanPreventivo,
    RecomendacionTecnica,
    Reprogramacion,
    User,
)
from app.models.enums import (
    Criticidad,
    EntidadEvidencia,
    EstadoActividad,
    EstadoActivo,
    EstadoNovedad,
    EstadoRecomendacion,
    Periodicidad,
    PrioridadNovedad,
    PrioridadRecomendacion,
    TipoMantenimiento,
    UserRole,
)
from app.schemas.activos_out import (
    ActividadOut,
    ActivoDetalle,
    ActivoResumen,
    ActivosPagina,
    AuditoriaOut,
    Color,
    ContratistaDetalle,
    ContratistaOut,
    DocumentoVinculado,
    EstadoHorasOut,
    EvidenciaOut,
    LecturaOut,
    MantenimientoDetalle,
    MantenimientoResumen,
    NovedadOut,
    PersonaOut,
    PlanOut,
    QrResuelto,
    RecomendacionOut,
    Ref,
    ReprogramacionOut,
    VencimientoOut,
)
from app.services.activos import activos as servicio_activos
from app.services.activos import catalogo, evidencias, mantenimientos, novedades, planes, qr, recomendaciones
from app.services.activos import semaforo as sem
from app.services.activos.dominio import (
    NOVEDAD_ABIERTA,
    PUEDE_VER,
    PUEDE_VER_COSTOS,
    peor_color,
    semaforo,
    vida_util_consumida,
)
from app.services.comun import Actor, NoEncontrado, exigir, hoy_bogota

PENDIENTES_RECOMENDACION = (EstadoRecomendacion.PENDIENTE, EstadoRecomendacion.EN_PROCESO)


@dataclass
class Contexto:
    """Nombres y permisos de la petición, cargados una sola vez."""

    actor: Actor
    hoy: date
    usuarios: dict[uuid.UUID, str] = field(default_factory=dict)
    contratistas: dict[uuid.UUID, str] = field(default_factory=dict)
    categorias: dict[uuid.UUID, str] = field(default_factory=dict)

    @property
    def costos(self) -> bool:
        return self.actor.role in PUEDE_VER_COSTOS

    def costo(self, valor: Decimal | None) -> Decimal | None:
        return valor if self.costos else None

    def usuario(self, uid: uuid.UUID | None) -> Ref | None:
        return Ref(id=uid, nombre=self.usuarios.get(uid, "Usuario")) if uid else None

    def contratista(self, cid: uuid.UUID | None) -> Ref | None:
        return Ref(id=cid, nombre=self.contratistas.get(cid, "Contratista")) if cid else None


async def contexto(db: AsyncSession, actor: Actor) -> Contexto:
    exigir(actor, PUEDE_VER, "consultar el módulo de mantenimiento")
    ctx = Contexto(actor, hoy_bogota())
    ctx.usuarios = {
        i: n
        for i, n in await db.execute(
            select(User.id, User.full_name)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.tenant_id == actor.tenant_id)
        )
    }
    ctx.contratistas = {i: n for i, n in await db.execute(select(Contratista.id, Contratista.razon_social))}
    ctx.categorias = {i: n for i, n in await db.execute(select(CategoriaActivo.id, CategoriaActivo.nombre))}
    return ctx


def _ref(id_: uuid.UUID, nombre: str) -> Ref:
    return Ref(id=id_, nombre=nombre)


async def _activos_por_id(db: AsyncSession, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Activo]:
    ids = set(ids)
    if not ids:
        return {}
    return {a.id: a for a in await db.scalars(select(Activo).where(Activo.id.in_(ids)))}


# --- Conversores ----------------------------------------------------------------------------


def _plan_out(
    ctx: Contexto, p: PlanPreventivo, activo: Activo, proxima: date | None = None, ejecuciones: int = 0
) -> PlanOut:
    return PlanOut(
        id=p.id,
        activo=_ref(activo.id, activo.nombre),
        activo_codigo=activo.codigo_interno,
        nombre=p.nombre,
        actividades_checklist=p.actividades_checklist,
        periodicidad=p.periodicidad,
        intervalo_horas=p.intervalo_horas,
        base_calculo=p.base_calculo,
        fecha_inicio=p.fecha_inicio,
        contratista=ctx.contratista(p.contratista_id),
        costo_estimado=ctx.costo(p.costo_estimado),
        aprobado=p.aprobado_at is not None,
        aprobado_por=ctx.usuario(p.aprobado_por_id),
        aprobado_at=p.aprobado_at,
        activo_plan=p.activo,
        proxima_fecha=proxima,
        ejecuciones=ejecuciones,
    )


def _actividad_out(
    ctx: Contexto,
    a: ActividadProgramada,
    plan: PlanPreventivo,
    activo: Activo,
    mantenimiento_id: uuid.UUID | None = None,
) -> ActividadOut:
    color: Color | None = None
    dias: int | None = None
    if a.estado == EstadoActividad.PROGRAMADA:
        color, dias = semaforo(a.fecha_programada, ctx.hoy)
    return ActividadOut(
        id=a.id,
        plan=_ref(plan.id, plan.nombre),
        activo=_ref(activo.id, activo.nombre),
        activo_codigo=activo.codigo_interno,
        ubicacion=activo.ubicacion,
        fecha_programada=a.fecha_programada,
        fecha_original=a.fecha_original,
        estado=a.estado,
        asignado_a=ctx.usuario(a.asignado_a_id),
        contratista=ctx.contratista(plan.contratista_id),
        semaforo=color,
        dias_restantes=dias,
        reprogramada=a.fecha_programada != a.fecha_original,
        mantenimiento_id=mantenimiento_id,
    )


def _mantenimiento_resumen(ctx: Contexto, m: MantenimientoEjecutado, activo: Activo) -> MantenimientoResumen:
    return MantenimientoResumen(
        id=m.id,
        codigo=m.codigo,
        activo=_ref(activo.id, activo.nombre),
        activo_codigo=activo.codigo_interno,
        tipo=m.tipo,
        fecha_ejecucion=m.fecha_ejecucion,
        nombre_tecnico=m.nombre_tecnico,
        contratista=ctx.contratista(m.contratista_id),
        estado_post_intervencion=m.estado_post_intervencion,
        costo_total=ctx.costo(m.costo_total),
        anulado=m.anulado_at is not None,
    )


def _novedad_out(ctx: Contexto, n: Novedad, activo: Activo, mantenimientos: list[Ref] | None = None) -> NovedadOut:
    sin_atender = None
    if n.estado == EstadoNovedad.REPORTADA and n.fecha_atencion is None:
        sin_atender = int((datetime.now(UTC) - n.fecha_reporte).total_seconds() // 3600)
    return NovedadOut(
        id=n.id,
        codigo=n.codigo,
        activo=_ref(activo.id, activo.nombre),
        activo_codigo=activo.codigo_interno,
        ubicacion=activo.ubicacion,
        fecha_reporte=n.fecha_reporte,
        reportado_por=ctx.usuario(n.reportado_por_id) or _ref(n.reportado_por_id, "Usuario"),
        descripcion=n.descripcion,
        riesgo_identificado=n.riesgo_identificado,
        prioridad=n.prioridad,
        estado=n.estado,
        contratista_asignado=ctx.contratista(n.contratista_asignado_id),
        asignado_a=ctx.usuario(n.asignado_a_id),
        cotizacion_id=n.cotizacion_id,
        fecha_atencion=n.fecha_atencion,
        diagnostico=n.diagnostico,
        solucion_implementada=n.solucion_implementada,
        costo_reparacion=ctx.costo(n.costo_reparacion),
        cerrada_por=ctx.usuario(n.cerrada_por_id),
        cerrada_at=n.cerrada_at,
        motivo_descarte=n.motivo_descarte,
        mantenimientos=mantenimientos or [],
        horas_sin_atender=sin_atender,
    )


def _recomendacion_out(
    ctx: Contexto, r: RecomendacionTecnica, activo: Activo, origen: MantenimientoEjecutado | None = None
) -> RecomendacionOut:
    return RecomendacionOut(
        id=r.id,
        activo=_ref(activo.id, activo.nombre),
        activo_codigo=activo.codigo_interno,
        mantenimiento_origen=_ref(origen.id, origen.codigo) if origen else None,
        descripcion=r.descripcion,
        prioridad=r.prioridad,
        estado=r.estado,
        responsable=ctx.usuario(r.responsable_id),
        fecha_limite=r.fecha_limite,
        vencida=bool(r.fecha_limite and r.fecha_limite < ctx.hoy and r.estado in PENDIENTES_RECOMENDACION),
        costo_estimado=ctx.costo(r.costo_estimado),
        observaciones_administracion=r.observaciones_administracion,
        justificacion_descarte=r.justificacion_descarte,
        mantenimiento_ejecucion_id=r.mantenimiento_ejecucion_id,
        created_at=r.created_at,
    )


# --- Activos ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class FiltroActivos:
    categoria_id: uuid.UUID | None = None
    ubicacion: str | None = None
    estado: EstadoActivo | None = None
    criticidad: Criticidad | None = None
    semaforo: Color | None = None
    texto: str | None = None
    incluir_bajas: bool = False


async def _proximas(db: AsyncSession) -> dict[uuid.UUID, tuple[Color, date]]:
    """Por activo: peor color de sus actividades pendientes y su próxima fecha."""
    colores: dict[uuid.UUID, list[Color]] = {}
    proxima: dict[uuid.UUID, date] = {}
    for a in await sem.actividades(db):
        colores.setdefault(a.activo_id, []).append(a.color)
        proxima.setdefault(a.activo_id, a.fecha_programada)  # vienen ordenadas por fecha
    return {k: (peor_color(v) or "VERDE", proxima[k]) for k, v in colores.items()}


async def buscar_activos(
    db: AsyncSession, actor: Actor, f: FiltroActivos, *, page: int = 1, page_size: int = 25
) -> ActivosPagina:
    ctx = await contexto(db, actor)
    q = select(Activo).order_by(Activo.consecutivo)
    if not f.incluir_bajas and f.estado != EstadoActivo.DADO_DE_BAJA:
        q = q.where(Activo.estado != EstadoActivo.DADO_DE_BAJA)
    if f.categoria_id:
        q = q.where(Activo.categoria_id == f.categoria_id)
    if f.ubicacion:
        q = q.where(Activo.ubicacion.ilike(f"%{f.ubicacion}%"))
    if f.estado:
        q = q.where(Activo.estado == f.estado)
    if f.criticidad:
        q = q.where(Activo.criticidad == f.criticidad)
    if f.texto:
        patron = f"%{f.texto}%"
        q = q.where(
            or_(
                Activo.nombre.ilike(patron),
                Activo.codigo_interno.ilike(patron),
                Activo.marca.ilike(patron),
                Activo.modelo.ilike(patron),
                Activo.numero_serie.ilike(patron),
                Activo.subtipo.ilike(patron),
            )
        )
    activos = list(await db.scalars(q))
    proximas = await _proximas(db)
    abiertas = dict(
        (
            await db.execute(
                select(Novedad.activo_id, func.count())
                .where(Novedad.estado.in_(NOVEDAD_ABIERTA))
                .group_by(Novedad.activo_id)
            )
        ).all()
    )
    filas = [
        ActivoResumen(
            id=a.id,
            codigo_interno=a.codigo_interno,
            nombre=a.nombre,
            categoria=_ref(a.categoria_id, ctx.categorias.get(a.categoria_id, "")),
            subtipo=a.subtipo,
            ubicacion=a.ubicacion,
            estado=a.estado,
            criticidad=a.criticidad,
            semaforo=proximas[a.id][0] if a.id in proximas else None,
            proxima_fecha=proximas[a.id][1] if a.id in proximas else None,
            novedades_abiertas=int(abiertas.get(a.id, 0)),
        )
        for a in activos
    ]
    por_semaforo = {c: sum(1 for x in filas if x.semaforo == c) for c in ("VERDE", "AMARILLO", "ROJO")}
    por_semaforo["SIN_PLAN"] = sum(1 for x in filas if x.semaforo is None)
    por_estado: dict[str, int] = {}
    for x in filas:
        por_estado[x.estado.value] = por_estado.get(x.estado.value, 0) + 1
    if f.semaforo:
        filas = [x for x in filas if x.semaforo == f.semaforo]
    inicio = (page - 1) * page_size
    return ActivosPagina(
        items=filas[inicio : inicio + page_size],
        total=len(filas),
        page=page,
        page_size=page_size,
        por_semaforo=por_semaforo,
        por_estado=por_estado,
    )


async def _ejecuciones_por_plan(db: AsyncSession, plan_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not plan_ids:
        return {}
    return dict(
        (
            await db.execute(
                select(ActividadProgramada.plan_id, func.count())
                .where(
                    ActividadProgramada.plan_id.in_(plan_ids), ActividadProgramada.estado == EstadoActividad.EJECUTADA
                )
                .group_by(ActividadProgramada.plan_id)
            )
        ).all()
    )


async def _proxima_por_plan(db: AsyncSession, plan_ids: list[uuid.UUID]) -> dict[uuid.UUID, date]:
    if not plan_ids:
        return {}
    return dict(
        (
            await db.execute(
                select(ActividadProgramada.plan_id, func.min(ActividadProgramada.fecha_programada))
                .where(
                    ActividadProgramada.plan_id.in_(plan_ids), ActividadProgramada.estado == EstadoActividad.PROGRAMADA
                )
                .group_by(ActividadProgramada.plan_id)
            )
        ).all()
    )


async def detalle_activo(db: AsyncSession, actor: Actor, activo_id: uuid.UUID, *, tenant_slug: str) -> ActivoDetalle:
    ctx = await contexto(db, actor)
    a = await servicio_activos.obtener(db, actor, activo_id)

    documentos = [
        DocumentoVinculado(
            document_id=v.document_id,
            titulo=titulo,
            tipo=v.tipo,
            fecha_documento=v.fecha_documento,
            vinculado_at=v.created_at,
        )
        for v, titulo in await db.execute(
            select(ActivoDocumento, Document.title)
            .join(Document, Document.id == ActivoDocumento.document_id)
            .where(ActivoDocumento.activo_id == a.id, Document.deleted_at.is_(None))
            .order_by(ActivoDocumento.created_at.desc())
        )
    ]
    vencimientos = [VencimientoOut.model_validate(v) for v in await servicio_activos.vencimientos(db, actor, a.id)]

    lista_planes = list(
        await db.scalars(
            select(PlanPreventivo).where(PlanPreventivo.activo_id == a.id).order_by(PlanPreventivo.created_at)
        )
    )
    ids_planes = [p.id for p in lista_planes]
    ejecuciones = await _ejecuciones_por_plan(db, ids_planes)
    proximas = await _proxima_por_plan(db, ids_planes)
    planes_out = [_plan_out(ctx, p, a, proximas.get(p.id), int(ejecuciones.get(p.id, 0))) for p in lista_planes]
    por_id = {p.id: p for p in lista_planes}

    pendientes = list(
        await db.scalars(
            select(ActividadProgramada)
            .where(ActividadProgramada.activo_id == a.id, ActividadProgramada.estado == EstadoActividad.PROGRAMADA)
            .order_by(ActividadProgramada.fecha_programada)
            .limit(12)
        )
    )
    color = peor_color([semaforo(x.fecha_programada, ctx.hoy)[0] for x in pendientes]) if pendientes else None

    mantenimientos = list(
        await db.scalars(
            select(MantenimientoEjecutado)
            .where(MantenimientoEjecutado.activo_id == a.id)
            .order_by(MantenimientoEjecutado.fecha_ejecucion.desc(), MantenimientoEjecutado.consecutivo.desc())
        )
    )
    vigentes = [m for m in mantenimientos if m.anulado_at is None]
    novedades = list(
        await db.scalars(select(Novedad).where(Novedad.activo_id == a.id).order_by(Novedad.fecha_reporte.desc()))
    )
    mto_por_novedad: dict[uuid.UUID, list[Ref]] = {}
    for m in vigentes:
        if m.novedad_id:
            mto_por_novedad.setdefault(m.novedad_id, []).append(_ref(m.id, m.codigo))
    origen = {m.id: m for m in mantenimientos}
    recomendaciones = list(
        await db.scalars(
            select(RecomendacionTecnica)
            .where(RecomendacionTecnica.activo_id == a.id)
            .order_by(RecomendacionTecnica.created_at.desc())
        )
    )
    lecturas = list(
        await db.scalars(
            select(LecturaUso).where(LecturaUso.activo_id == a.id).order_by(LecturaUso.fecha.desc()).limit(20)
        )
    )
    horas = []
    for p in lista_planes:
        if p.periodicidad == Periodicidad.POR_HORAS_USO and p.activo and p.intervalo_horas:
            medicion = await planes.medir_horas(db, p, ctx.hoy)
            if medicion is not None:
                horas.append(
                    EstadoHorasOut(
                        plan_id=p.id,
                        intervalo_horas=p.intervalo_horas,
                        horas_desde_ultimo=medicion.horas_desde_ultimo,
                        horas_restantes=medicion.estado.horas_restantes,
                        uso_diario=medicion.uso_diario.quantize(Decimal("0.1")) if medicion.uso_diario else None,
                        fecha_estimada=medicion.estado.fecha_estimada,
                    )
                )
    anio = ctx.hoy.year
    return ActivoDetalle(
        id=a.id,
        codigo_interno=a.codigo_interno,
        qr_token=a.qr_token,
        qr_url=qr.url_qr(tenant_slug, a.qr_token),
        nombre=a.nombre,
        categoria=_ref(a.categoria_id, ctx.categorias.get(a.categoria_id, "")),
        subtipo=a.subtipo,
        ubicacion=a.ubicacion,
        marca=a.marca,
        modelo=a.modelo,
        fabricante=a.fabricante,
        numero_serie=a.numero_serie,
        especificaciones=a.especificaciones,
        vida_util_anios=a.vida_util_anios,
        vida_util_consumida=vida_util_consumida(a.fecha_instalacion, a.vida_util_anios, ctx.hoy),
        fecha_instalacion=a.fecha_instalacion,
        instalador=ctx.contratista(a.instalador_id),
        mantenedor=ctx.contratista(a.mantenedor_id),
        fecha_vencimiento_garantia=a.fecha_vencimiento_garantia,
        garantia_vigente=a.fecha_vencimiento_garantia >= ctx.hoy if a.fecha_vencimiento_garantia else None,
        criticidad=a.criticidad,
        estado=a.estado,
        motivo_baja=a.motivo_baja,
        fecha_baja=a.fecha_baja,
        semaforo=color,
        created_at=a.created_at,
        updated_at=a.updated_at,
        documentos=documentos,
        vencimientos=vencimientos,
        planes=planes_out,
        proximas_actividades=[_actividad_out(ctx, x, por_id[x.plan_id], a) for x in pendientes],
        mantenimientos=[_mantenimiento_resumen(ctx, m, a) for m in mantenimientos],
        novedades=[_novedad_out(ctx, n, a, mto_por_novedad.get(n.id)) for n in novedades],
        recomendaciones=[
            _recomendacion_out(ctx, r, a, origen.get(r.mantenimiento_origen_id) if r.mantenimiento_origen_id else None)
            for r in recomendaciones
        ],
        lecturas=[LecturaOut.model_validate(x) for x in lecturas],
        horas=horas,
        costo_acumulado=ctx.costo(sum((m.costo_total for m in vigentes), Decimal(0))),
        costo_anio=ctx.costo(sum((m.costo_total for m in vigentes if m.fecha_ejecucion.year == anio), Decimal(0))),
        puede_ver_costos=ctx.costos,
    )


async def resolver_qr(db: AsyncSession, actor: Actor, token: str) -> QrResuelto:
    ctx = await contexto(db, actor)
    a = await servicio_activos.por_qr(db, actor, token)
    ultimo = await db.scalar(
        select(MantenimientoEjecutado)
        .where(MantenimientoEjecutado.activo_id == a.id, MantenimientoEjecutado.anulado_at.is_(None))
        .order_by(MantenimientoEjecutado.fecha_ejecucion.desc(), MantenimientoEjecutado.consecutivo.desc())
        .limit(1)
    )
    pendientes = list(
        await db.scalars(
            select(ActividadProgramada)
            .where(ActividadProgramada.activo_id == a.id, ActividadProgramada.estado == EstadoActividad.PROGRAMADA)
            .order_by(ActividadProgramada.fecha_programada)
        )
    )
    proxima = None
    if pendientes:
        plan = await db.get(PlanPreventivo, pendientes[0].plan_id)
        assert plan is not None
        proxima = _actividad_out(ctx, pendientes[0], plan, a)
    abiertas = await db.scalars(
        select(Novedad)
        .where(Novedad.activo_id == a.id, Novedad.estado.in_(NOVEDAD_ABIERTA))
        .order_by(Novedad.fecha_reporte.desc())
    )
    usa_horometro = bool(
        await db.scalar(
            select(func.count()).where(
                PlanPreventivo.activo_id == a.id,
                PlanPreventivo.periodicidad == Periodicidad.POR_HORAS_USO,
                PlanPreventivo.activo,
            )
        )
    )
    return QrResuelto(
        id=a.id,
        codigo_interno=a.codigo_interno,
        nombre=a.nombre,
        ubicacion=a.ubicacion,
        estado=a.estado,
        criticidad=a.criticidad,
        semaforo=peor_color([semaforo(x.fecha_programada, ctx.hoy)[0] for x in pendientes]) if pendientes else None,
        ultimo_mantenimiento=_mantenimiento_resumen(ctx, ultimo, a) if ultimo else None,
        proxima_actividad=proxima,
        novedades_abiertas=[_novedad_out(ctx, n, a) for n in abiertas],
        usa_horometro=usa_horometro,
    )


async def lecturas(db: AsyncSession, actor: Actor, activo_id: uuid.UUID) -> list[LecturaOut]:
    await servicio_activos.obtener(db, actor, activo_id)
    filas = await db.scalars(
        select(LecturaUso).where(LecturaUso.activo_id == activo_id).order_by(LecturaUso.fecha.desc())
    )
    return [LecturaOut.model_validate(x) for x in filas]


# --- Planes y actividades -------------------------------------------------------------------


async def listar_planes(
    db: AsyncSession, actor: Actor, *, activo_id: uuid.UUID | None = None, pendientes_aprobacion: bool = False
) -> list[PlanOut]:
    ctx = await contexto(db, actor)
    q = select(PlanPreventivo).order_by(PlanPreventivo.created_at)
    if activo_id:
        q = q.where(PlanPreventivo.activo_id == activo_id)
    if pendientes_aprobacion:
        q = q.where(PlanPreventivo.aprobado_at.is_(None), PlanPreventivo.activo)
    lista = list(await db.scalars(q))
    activos = await _activos_por_id(db, (p.activo_id for p in lista))
    ids = [p.id for p in lista]
    ejecuciones, proximas = await _ejecuciones_por_plan(db, ids), await _proxima_por_plan(db, ids)
    return [_plan_out(ctx, p, activos[p.activo_id], proximas.get(p.id), int(ejecuciones.get(p.id, 0))) for p in lista]


async def plan(db: AsyncSession, actor: Actor, plan_id: uuid.UUID) -> PlanOut:
    ctx = await contexto(db, actor)
    p = await planes.obtener_plan(db, actor, plan_id)
    activo = await db.get(Activo, p.activo_id)
    assert activo is not None
    ejecuciones, proximas = await _ejecuciones_por_plan(db, [p.id]), await _proxima_por_plan(db, [p.id])
    return _plan_out(ctx, p, activo, proximas.get(p.id), int(ejecuciones.get(p.id, 0)))


@dataclass(frozen=True)
class FiltroActividades:
    desde: date | None = None
    hasta: date | None = None
    activo_id: uuid.UUID | None = None
    plan_id: uuid.UUID | None = None
    estado: EstadoActividad | None = None
    semaforo: Color | None = None
    asignado_a_id: uuid.UUID | None = None
    mias: bool = False


async def listar_actividades(db: AsyncSession, actor: Actor, f: FiltroActividades) -> list[ActividadOut]:
    """Calendario y cronograma. Sin rango: las vencidas y los próximos 60 días."""
    ctx = await contexto(db, actor)
    q = select(ActividadProgramada).order_by(ActividadProgramada.fecha_programada)
    if f.desde or f.hasta:
        if f.desde:
            q = q.where(ActividadProgramada.fecha_programada >= f.desde)
        if f.hasta:
            q = q.where(ActividadProgramada.fecha_programada <= f.hasta)
    else:
        q = q.where(
            ActividadProgramada.estado == EstadoActividad.PROGRAMADA,
            ActividadProgramada.fecha_programada <= ctx.hoy + timedelta(days=60),
        )
    for columna, valor in (
        (ActividadProgramada.activo_id, f.activo_id),
        (ActividadProgramada.plan_id, f.plan_id),
        (ActividadProgramada.estado, f.estado),
        (ActividadProgramada.asignado_a_id, f.asignado_a_id),
    ):
        if valor is not None:
            q = q.where(columna == valor)
    if f.mias:
        q = q.where(ActividadProgramada.asignado_a_id == actor.user_id)
    lista = list(await db.scalars(q.limit(2000)))
    planes_ = {
        p.id: p
        for p in await db.scalars(select(PlanPreventivo).where(PlanPreventivo.id.in_({x.plan_id for x in lista})))
    }
    activos = await _activos_por_id(db, (x.activo_id for x in lista))
    ejecutadas = [x.id for x in lista if x.estado == EstadoActividad.EJECUTADA]
    mto = (
        dict(
            (
                await db.execute(
                    select(MantenimientoEjecutado.actividad_id, MantenimientoEjecutado.id).where(
                        MantenimientoEjecutado.actividad_id.in_(ejecutadas), MantenimientoEjecutado.anulado_at.is_(None)
                    )
                )
            ).all()
        )
        if ejecutadas
        else {}
    )
    salida = [_actividad_out(ctx, x, planes_[x.plan_id], activos[x.activo_id], mto.get(x.id)) for x in lista]
    if f.semaforo:
        salida = [x for x in salida if x.semaforo == f.semaforo]
    return salida


async def actividad(db: AsyncSession, actor: Actor, actividad_id: uuid.UUID) -> ActividadOut:
    ctx = await contexto(db, actor)
    x = await planes.obtener_actividad(db, actor, actividad_id)
    p, a = await db.get(PlanPreventivo, x.plan_id), await db.get(Activo, x.activo_id)
    assert p is not None and a is not None
    mid = await db.scalar(
        select(MantenimientoEjecutado.id).where(
            MantenimientoEjecutado.actividad_id == x.id, MantenimientoEjecutado.anulado_at.is_(None)
        )
    )
    return _actividad_out(ctx, x, p, a, mid)


async def reprogramaciones(db: AsyncSession, actor: Actor, actividad_id: uuid.UUID) -> list[ReprogramacionOut]:
    await planes.obtener_actividad(db, actor, actividad_id)
    filas = await db.scalars(
        select(Reprogramacion).where(Reprogramacion.actividad_id == actividad_id).order_by(Reprogramacion.created_at)
    )
    return [ReprogramacionOut.model_validate(r) for r in filas]


# --- Mantenimientos ----------------------------------------------------------------------------


async def listar_mantenimientos(
    db: AsyncSession,
    actor: Actor,
    *,
    activo_id: uuid.UUID | None = None,
    tipo: TipoMantenimiento | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    contratista_id: uuid.UUID | None = None,
    incluir_anulados: bool = True,
    limite: int = 200,
) -> list[MantenimientoResumen]:
    ctx = await contexto(db, actor)
    q = select(MantenimientoEjecutado).order_by(
        MantenimientoEjecutado.fecha_ejecucion.desc(), MantenimientoEjecutado.consecutivo.desc()
    )
    for columna, valor in (
        (MantenimientoEjecutado.activo_id, activo_id),
        (MantenimientoEjecutado.tipo, tipo),
        (MantenimientoEjecutado.contratista_id, contratista_id),
    ):
        if valor is not None:
            q = q.where(columna == valor)
    if desde:
        q = q.where(MantenimientoEjecutado.fecha_ejecucion >= desde)
    if hasta:
        q = q.where(MantenimientoEjecutado.fecha_ejecucion <= hasta)
    if not incluir_anulados:
        q = q.where(MantenimientoEjecutado.anulado_at.is_(None))
    lista = list(await db.scalars(q.limit(limite)))
    activos = await _activos_por_id(db, (m.activo_id for m in lista))
    return [_mantenimiento_resumen(ctx, m, activos[m.activo_id]) for m in lista]


async def detalle_mantenimiento(db: AsyncSession, actor: Actor, mantenimiento_id: uuid.UUID) -> MantenimientoDetalle:
    ctx = await contexto(db, actor)
    m = await mantenimientos.obtener(db, actor, mantenimiento_id)
    activo = await db.get(Activo, m.activo_id)
    assert activo is not None
    plan_ref = None
    if m.actividad_id:
        fila = (
            await db.execute(
                select(PlanPreventivo.id, PlanPreventivo.nombre)
                .join(ActividadProgramada, ActividadProgramada.plan_id == PlanPreventivo.id)
                .where(ActividadProgramada.id == m.actividad_id)
            )
        ).first()
        plan_ref = _ref(*fila) if fila else None
    novedad_ref = None
    if m.novedad_id:
        codigo = await db.scalar(select(Novedad.codigo).where(Novedad.id == m.novedad_id))
        novedad_ref = _ref(m.novedad_id, codigo or "Novedad")
    recs = await db.scalars(
        select(RecomendacionTecnica)
        .where(RecomendacionTecnica.mantenimiento_origen_id == m.id)
        .order_by(RecomendacionTecnica.created_at)
    )
    base = _mantenimiento_resumen(ctx, m, activo)
    return MantenimientoDetalle(
        **base.model_dump(),
        tiempo_ejecucion_horas=m.tiempo_ejecucion_horas,
        diagnostico_inicial=m.diagnostico_inicial,
        actividades_realizadas=m.actividades_realizadas,
        repuestos_utilizados=m.repuestos_utilizados,
        novedades_encontradas=m.novedades_encontradas,
        recomendaciones_tecnico=m.recomendaciones_tecnico,
        checklist=m.checklist,
        costo_mano_obra=ctx.costo(m.costo_mano_obra),
        costo_repuestos=ctx.costo(m.costo_repuestos),
        fecha_proximo_recomendado=m.fecha_proximo_recomendado,
        actividad_id=m.actividad_id,
        plan=plan_ref,
        novedad=novedad_ref,
        informe_documento_id=m.informe_documento_id,  # el informe técnico lo ve todo el personal
        factura_documento_id=m.factura_documento_id if ctx.costos else None,  # la factura, solo quien ve costos
        registrado_por=ctx.usuario(m.registrado_por_id) or _ref(m.registrado_por_id, "Usuario"),
        created_at=m.created_at,
        anulado_por=ctx.usuario(m.anulado_por_id),
        anulado_at=m.anulado_at,
        motivo_anulacion=m.motivo_anulacion,
        recomendaciones=[_recomendacion_out(ctx, r, activo, m) for r in recs],
    )


# --- Novedades y recomendaciones ----------------------------------------------------------------


async def listar_novedades(
    db: AsyncSession,
    actor: Actor,
    *,
    estados: list[EstadoNovedad] | None = None,
    abiertas: bool = False,
    prioridad: PrioridadNovedad | None = None,
    activo_id: uuid.UUID | None = None,
    mias: bool = False,
) -> list[NovedadOut]:
    ctx = await contexto(db, actor)
    q = select(Novedad).order_by(Novedad.fecha_reporte.desc())
    if estados:
        q = q.where(Novedad.estado.in_(estados))
    if abiertas:
        q = q.where(Novedad.estado.in_(NOVEDAD_ABIERTA))
    if prioridad:
        q = q.where(Novedad.prioridad == prioridad)
    if activo_id:
        q = q.where(Novedad.activo_id == activo_id)
    if mias:
        q = q.where(or_(Novedad.asignado_a_id == actor.user_id, Novedad.reportado_por_id == actor.user_id))
    lista = list(await db.scalars(q.limit(500)))
    activos = await _activos_por_id(db, (n.activo_id for n in lista))
    mto: dict[uuid.UUID, list[Ref]] = {}
    if lista:
        for mid, codigo, nid in await db.execute(
            select(MantenimientoEjecutado.id, MantenimientoEjecutado.codigo, MantenimientoEjecutado.novedad_id).where(
                MantenimientoEjecutado.novedad_id.in_([n.id for n in lista]),
                MantenimientoEjecutado.anulado_at.is_(None),
            )
        ):
            mto.setdefault(nid, []).append(_ref(mid, codigo))
    return [_novedad_out(ctx, n, activos[n.activo_id], mto.get(n.id)) for n in lista]


async def novedad(db: AsyncSession, actor: Actor, novedad_id: uuid.UUID) -> NovedadOut:
    ctx = await contexto(db, actor)
    n = await novedades.obtener(db, actor, novedad_id)
    activo = await db.get(Activo, n.activo_id)
    assert activo is not None
    mto = [
        _ref(i, c)
        for i, c in await db.execute(
            select(MantenimientoEjecutado.id, MantenimientoEjecutado.codigo).where(
                MantenimientoEjecutado.novedad_id == n.id, MantenimientoEjecutado.anulado_at.is_(None)
            )
        )
    ]
    return _novedad_out(ctx, n, activo, mto)


async def listar_recomendaciones(
    db: AsyncSession,
    actor: Actor,
    *,
    estado: EstadoRecomendacion | None = None,
    pendientes: bool = False,
    prioridad: PrioridadRecomendacion | None = None,
    activo_id: uuid.UUID | None = None,
    mias: bool = False,
) -> list[RecomendacionOut]:
    ctx = await contexto(db, actor)
    q = select(RecomendacionTecnica).order_by(RecomendacionTecnica.created_at.desc())
    if estado:
        q = q.where(RecomendacionTecnica.estado == estado)
    if pendientes:
        q = q.where(RecomendacionTecnica.estado.in_(PENDIENTES_RECOMENDACION))
    if prioridad:
        q = q.where(RecomendacionTecnica.prioridad == prioridad)
    if activo_id:
        q = q.where(RecomendacionTecnica.activo_id == activo_id)
    if mias:
        q = q.where(RecomendacionTecnica.responsable_id == actor.user_id)
    lista = list(await db.scalars(q.limit(500)))
    activos = await _activos_por_id(db, (r.activo_id for r in lista))
    origen_ids = {r.mantenimiento_origen_id for r in lista if r.mantenimiento_origen_id}
    origenes = (
        {
            m.id: m
            for m in await db.scalars(select(MantenimientoEjecutado).where(MantenimientoEjecutado.id.in_(origen_ids)))
        }
        if origen_ids
        else {}
    )
    return [
        _recomendacion_out(ctx, r, activos[r.activo_id], origenes.get(r.mantenimiento_origen_id))  # type: ignore[arg-type]
        for r in lista
    ]


async def recomendacion(db: AsyncSession, actor: Actor, recomendacion_id: uuid.UUID) -> RecomendacionOut:
    ctx = await contexto(db, actor)
    r = await recomendaciones.obtener(db, actor, recomendacion_id)
    activo = await db.get(Activo, r.activo_id)
    assert activo is not None
    origen = await db.get(MantenimientoEjecutado, r.mantenimiento_origen_id) if r.mantenimiento_origen_id else None
    return _recomendacion_out(ctx, r, activo, origen)


# --- Catálogo, evidencias y auditoría ---------------------------------------------------------


async def contratista_detalle(db: AsyncSession, actor: Actor, contratista_id: uuid.UUID) -> ContratistaDetalle:
    ctx = await contexto(db, actor)
    c = await catalogo.contratista(db, actor, contratista_id)
    assert c is not None
    activos = [
        _ref(i, f"{cod} {n}")
        for i, cod, n in await db.execute(
            select(Activo.id, Activo.codigo_interno, Activo.nombre)
            .where(or_(Activo.mantenedor_id == c.id, Activo.instalador_id == c.id))
            .order_by(Activo.consecutivo)
        )
    ]
    total, correctivos, costo = (
        await db.execute(
            select(
                func.count(),
                func.count().filter(MantenimientoEjecutado.tipo == TipoMantenimiento.CORRECTIVO),
                func.coalesce(func.sum(MantenimientoEjecutado.costo_total), 0),
            ).where(MantenimientoEjecutado.contratista_id == c.id, MantenimientoEjecutado.anulado_at.is_(None))
        )
    ).one()
    base = ContratistaOut.model_validate(c).model_dump()
    base["valor_contrato"] = ctx.costo(c.valor_contrato)
    return ContratistaDetalle(
        **base,
        activos=activos,
        mantenimientos=int(total),
        correctivos=int(correctivos),
        costo_total=ctx.costo(Decimal(costo)),
    )


def contratista_out(actor: Actor, c: Contratista) -> ContratistaOut:
    out = ContratistaOut.model_validate(c)
    return out if actor.role in PUEDE_VER_COSTOS else out.model_copy(update={"valor_contrato": None})


async def personal(db: AsyncSession, actor: Actor) -> list[PersonaOut]:
    """Personas a las que se puede asignar trabajo (administración y mantenimiento)."""
    exigir(actor, PUEDE_VER, "consultar el personal")
    filas = await db.execute(
        select(User.id, User.full_name, Membership.role)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.tenant_id == actor.tenant_id,
            User.is_active,
            Membership.role.in_([UserRole.ADMIN, UserRole.AUXILIAR, UserRole.MANTENIMIENTO]),
        )
        .order_by(User.full_name)
    )
    return [PersonaOut(id=i, nombre=n, rol=r.value) for i, n, r in filas]


def evidencia_out(ctx: Contexto, e: Evidencia, url: str) -> EvidenciaOut:
    return EvidenciaOut(
        id=e.id,
        entidad=e.entidad,
        entidad_id=e.entidad_id,
        momento=e.momento,
        content_type=e.content_type,
        size_bytes=e.size_bytes,
        descripcion=e.descripcion,
        subido_por=ctx.usuario(e.subido_por_id),
        created_at=e.created_at,
        url=url,
    )


async def listar_evidencias(
    db: AsyncSession, actor: Actor, entidad: EntidadEvidencia, entidad_id: uuid.UUID
) -> list[EvidenciaOut]:

    ctx = await contexto(db, actor)
    return [evidencia_out(ctx, e, url) for e, url in await evidencias.listar(db, actor, entidad, entidad_id)]


ENTIDADES_AUDITORIA = frozenset(
    {"activo", "plan", "actividad", "mantenimiento", "novedad", "recomendacion", "contratista"}
)


async def auditoria(db: AsyncSession, actor: Actor, entidad: str, entidad_id: uuid.UUID) -> list[AuditoriaOut]:
    """Trazabilidad de un registro. Para un activo incluye también lo ocurrido en sus planes,
    actividades, mantenimientos y novedades."""
    ctx = await contexto(db, actor)
    if entidad not in ENTIDADES_AUDITORIA:
        raise NoEncontrado("Tipo de registro desconocido")
    q = select(AuditoriaActivo).order_by(AuditoriaActivo.fecha_hora.desc(), AuditoriaActivo.id.desc()).limit(500)
    if entidad == "activo":
        q = q.where(or_(AuditoriaActivo.entidad_id == entidad_id, AuditoriaActivo.activo_id == entidad_id))
    else:
        q = q.where(AuditoriaActivo.entidad == entidad, AuditoriaActivo.entidad_id == entidad_id)
    return [
        AuditoriaOut(
            id=x.id,
            entidad=x.entidad,
            entidad_id=x.entidad_id,
            accion=x.accion,
            usuario=ctx.usuario(x.usuario_id),
            valores_anteriores=_sin_costos(ctx, x.valores_anteriores),
            valores_nuevos=_sin_costos(ctx, x.valores_nuevos),
            motivo=x.motivo,
            fecha_hora=x.fecha_hora,
        )
        for x in await db.scalars(q)
    ]


_CAMPOS_COSTO = ("costo", "valor")


def _sin_costos(ctx: Contexto, valores: dict[str, object] | None) -> dict[str, object] | None:
    if valores is None or ctx.costos:
        return valores
    return {k: v for k, v in valores.items() if not k.startswith(_CAMPOS_COSTO)}
