"""Reportes del módulo de mantenimiento (docs/MANTENIMIENTO.md §5).

Usan el motor de recaudos: cada informe se arma una vez como `Reporte` (resumen +
tablas) y se dibuja en pantalla, Excel y PDF con las mismas cifras
(app/services/recaudos/exportar.py). Los datos pasan por las consultas del
módulo: RLS por rol y costos ocultos a quien no debe verlos.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

import pymupdf
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ActividadProgramada,
    Activo,
    CategoriaActivo,
    Contratista,
    MantenimientoEjecutado,
    Novedad,
    PlanPreventivo,
    RecomendacionTecnica,
    Tenant,
)
from app.models.enums import EstadoActividad, EstadoActivo, EstadoNovedad, Periodicidad, TipoMantenimiento, UserRole
from app.services.activos import consultas, panel, qr
from app.services.activos.consultas import Contexto
from app.services.activos.dominio import NOVEDAD_ABIERTA, PUEDE_VER, vida_util_consumida
from app.services.comun import TZ, Actor, ValidacionError, exigir, hoy_bogota, pesos
from app.services.recaudos.exportar import a_pdf
from app.services.recaudos.reportes import Columna, Reporte, Tabla

R = UserRole
TipoReporteActivos = Literal[
    "inventario", "cumplimiento", "correctivos", "recomendaciones", "costos", "infraestructura"
]

GESTION = frozenset({R.ADMIN, R.AUXILIAR, R.CONTABILIDAD})
PERMISOS: dict[str, frozenset[UserRole]] = {
    "inventario": PUEDE_VER,
    "cumplimiento": GESTION,
    "correctivos": GESTION,
    "recomendaciones": GESTION,
    "costos": frozenset({R.ADMIN, R.CONTABILIDAD}),
    "infraestructura": GESTION,
    "dossier": PUEDE_VER,
}
TITULOS = {
    "inventario": "Inventario y hojas de vida",
    "cumplimiento": "Cumplimiento del plan preventivo",
    "correctivos": "Correctivos y novedades",
    "recomendaciones": "Matriz de recomendaciones técnicas",
    "costos": "Costos y proyección presupuestal",
    "infraestructura": "Estado de la infraestructura",
    "dossier": "Hoja de vida del activo",
}
CON_PERIODO = {"cumplimiento", "correctivos", "costos"}  # los demás son un corte a hoy
ESTADO_TXT = {
    EstadoActivo.OPERATIVO: "Operativo",
    EstadoActivo.OPERATIVO_CON_OBSERVACIONES: "Con observaciones",
    EstadoActivo.EN_MANTENIMIENTO: "En mantenimiento",
    EstadoActivo.FUERA_DE_SERVICIO: "Fuera de servicio",
    EstadoActivo.DADO_DE_BAJA: "Dado de baja",
}
TIPO_TXT = {
    TipoMantenimiento.PREVENTIVO: "Preventivo",
    TipoMantenimiento.CORRECTIVO: "Correctivo",
    TipoMantenimiento.PREDICTIVO: "Predictivo",
    TipoMantenimiento.INSPECCION_TECNICA: "Inspección técnica",
}
PERIODICIDAD_TXT = {
    Periodicidad.SEMANAL: "Semanal",
    Periodicidad.QUINCENAL: "Quincenal",
    Periodicidad.MENSUAL: "Mensual",
    Periodicidad.BIMESTRAL: "Bimestral",
    Periodicidad.TRIMESTRAL: "Trimestral",
    Periodicidad.SEMESTRAL: "Semestral",
    Periodicidad.ANUAL: "Anual",
    Periodicidad.POR_HORAS_USO: "Por horas de uso",
}
VECES_AL_ANIO = {
    Periodicidad.SEMANAL: 52,
    Periodicidad.QUINCENAL: 24,
    Periodicidad.MENSUAL: 12,
    Periodicidad.BIMESTRAL: 6,
    Periodicidad.TRIMESTRAL: 4,
    Periodicidad.SEMESTRAL: 2,
    Periodicidad.ANUAL: 1,
}
PESO_PRIORIDAD = {"ALTA": Decimal(1), "MEDIA": Decimal("0.6"), "BAJA": Decimal("0.3")}
MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
MESES_LARGOS = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


@dataclass
class ReporteActivos(Reporte):
    corte: bool = False

    @property
    def periodo(self) -> str:
        if self.corte:
            d = self.hasta
            return f"Corte al {d.day} de {MESES_LARGOS[d.month - 1]} de {d.year}"
        return super().periodo


def _n(nombre: str | None) -> str:
    return (nombre or "").split(" (")[0]


def _porc(parte: int | Decimal, total: int | Decimal) -> Decimal | None:
    return (Decimal(parte) * 100 / Decimal(total)).quantize(Decimal("0.1")) if total else None


def _txt_porc(p: Decimal | None) -> str:
    return "—" if p is None else f"{p} %".replace(".", ",")


def _horas(desde: datetime, hasta: datetime | None) -> Decimal | None:
    return Decimal((hasta - desde).total_seconds() / 3600).quantize(Decimal("0.1")) if hasta else None


def _local(dt: datetime) -> date:
    return dt.astimezone(TZ).date()


async def _activos(db: AsyncSession) -> dict[uuid.UUID, Activo]:
    return {a.id: a for a in await db.scalars(select(Activo).order_by(Activo.consecutivo))}


# --- 1. Inventario --------------------------------------------------------------------


async def _inventario(
    db: AsyncSession, actor: Actor, ctx: Contexto, desde: date, hasta: date
) -> tuple[list[tuple[str, str]], list[Tabla]]:
    activos = [a for a in (await _activos(db)).values() if a.estado != EstadoActivo.DADO_DE_BAJA]
    proximas = await consultas._proximas(db)
    filas = []
    por_categoria: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for a in activos:
        color, prox = proximas.get(a.id, (None, None))
        vida = vida_util_consumida(a.fecha_instalacion, a.vida_util_anios, ctx.hoy)
        filas.append(
            [
                a.codigo_interno,
                a.nombre,
                ctx.categorias.get(a.categoria_id, ""),
                a.subtipo or "",
                a.ubicacion,
                " ".join(x for x in (a.marca, a.modelo) if x),
                a.fecha_instalacion,
                vida,
                ESTADO_TXT[a.estado],
                a.criticidad.value.capitalize(),
                {"VERDE": "Al día", "AMARILLO": "Próximo", "ROJO": "Vencido"}.get(color or "", "Sin plan"),
                prox,
                ctx.contratistas.get(a.mantenedor_id, "Personal interno") if a.mantenedor_id else "Personal interno",
            ]
        )
        c = por_categoria[ctx.categorias.get(a.categoria_id, "")]
        c[0] += 1
        c[1] += a.estado == EstadoActivo.FUERA_DE_SERVICIO
        c[2] += color == "ROJO"
    resumen = [
        ("Activos vigentes", str(len(activos))),
        ("Operativos", str(sum(a.estado == EstadoActivo.OPERATIVO for a in activos))),
        ("Con observaciones", str(sum(a.estado == EstadoActivo.OPERATIVO_CON_OBSERVACIONES for a in activos))),
        ("Fuera de servicio", str(sum(a.estado == EstadoActivo.FUERA_DE_SERVICIO for a in activos))),
        ("Con mantenimiento vencido", str(sum(proximas.get(a.id, (None,))[0] == "ROJO" for a in activos))),
    ]
    tablas = [
        Tabla(
            "Activos",
            [
                Columna("Código"),
                Columna("Activo"),
                Columna("Categoría"),
                Columna("Tipo"),
                Columna("Ubicación"),
                Columna("Marca y modelo"),
                Columna("Instalación", "fecha"),
                Columna("Vida útil consumida", "porcentaje"),
                Columna("Estado"),
                Columna("Criticidad"),
                Columna("Mantenimiento"),
                Columna("Próxima fecha", "fecha"),
                Columna("A cargo de"),
            ],
            filas,
        ),
        Tabla(
            "Por categoría",
            [
                Columna("Categoría"),
                Columna("Activos", "entero"),
                Columna("Fuera de servicio", "entero"),
                Columna("Con vencidos", "entero"),
            ],
            [[k, *v] for k, v in sorted(por_categoria.items())],
            totales=[
                "Total",
                len(activos),
                sum(v[1] for v in por_categoria.values()),
                sum(v[2] for v in por_categoria.values()),
            ],
        ),
    ]
    return resumen, tablas


# --- 2. Cumplimiento ---------------------------------------------------------------------


async def _cumplimiento(
    db: AsyncSession, actor: Actor, ctx: Contexto, desde: date, hasta: date
) -> tuple[list[tuple[str, str]], list[Tabla]]:
    tope = min(hasta, ctx.hoy)
    actividades = list(
        await db.scalars(
            select(ActividadProgramada).where(
                ActividadProgramada.fecha_programada >= desde,
                ActividadProgramada.fecha_programada <= tope,
                ActividadProgramada.estado != EstadoActividad.CANCELADA,
            )
        )
    )
    ejecucion = (
        dict(
            (
                await db.execute(
                    select(MantenimientoEjecutado.actividad_id, MantenimientoEjecutado.fecha_ejecucion).where(
                        MantenimientoEjecutado.actividad_id.in_([x.id for x in actividades]),
                        MantenimientoEjecutado.anulado_at.is_(None),
                    )
                )
            ).all()
        )
        if actividades
        else {}
    )
    planes = {p.id: p for p in await db.scalars(select(PlanPreventivo))}
    activos = await _activos(db)
    por_plan: dict[uuid.UUID, list[int]] = defaultdict(lambda: [0, 0, 0])
    pendientes = []
    for x in actividades:
        fila = por_plan[x.plan_id]
        fila[0] += 1
        if x.estado == EstadoActividad.EJECUTADA:
            fila[1] += 1
            f = ejecucion.get(x.id)
            fila[2] += bool(f and f <= x.fecha_programada)
        else:
            a = activos[x.activo_id]
            pendientes.append(
                [
                    a.codigo_interno,
                    a.nombre,
                    planes[x.plan_id].nombre,
                    x.fecha_programada,
                    (ctx.hoy - x.fecha_programada).days,
                    _n(ctx.usuarios.get(x.asignado_a_id)) if x.asignado_a_id else "",
                ]
            )
    total = sum(v[0] for v in por_plan.values())
    hechas = sum(v[1] for v in por_plan.values())
    a_tiempo = sum(v[2] for v in por_plan.values())
    filas = []
    for pid, (prog, ejec, tiempo) in sorted(
        por_plan.items(), key=lambda kv: activos[planes[kv[0]].activo_id].consecutivo
    ):
        p = planes[pid]
        a = activos[p.activo_id]
        filas.append(
            [
                a.codigo_interno,
                a.nombre,
                p.nombre,
                PERIODICIDAD_TXT[p.periodicidad],
                prog,
                ejec,
                tiempo,
                _porc(ejec, prog),
            ]
        )
    resumen = [
        ("Actividades con fecha cumplida en el periodo", str(total)),
        ("Ejecutadas", str(hechas)),
        ("Cumplimiento", _txt_porc(_porc(hechas, total))),
        ("Ejecutadas a tiempo (en o antes de su fecha)", _txt_porc(_porc(a_tiempo, total))),
        ("Pendientes vencidas", str(len(pendientes))),
    ]
    tablas = [
        Tabla(
            "Por plan",
            [
                Columna("Código"),
                Columna("Activo"),
                Columna("Plan"),
                Columna("Periodicidad"),
                Columna("Programadas", "entero"),
                Columna("Ejecutadas", "entero"),
                Columna("A tiempo", "entero"),
                Columna("Cumplimiento", "porcentaje"),
            ],
            filas,
            totales=["Total", "", "", "", total, hechas, a_tiempo, _porc(hechas, total)],
            nota="Una actividad ejecutada tarde cuenta como cumplida; «a tiempo» es la que se ejecutó en o antes de su fecha.",
        ),
        Tabla(
            "Pendientes vencidas",
            [
                Columna("Código"),
                Columna("Activo"),
                Columna("Plan"),
                Columna("Fecha", "fecha"),
                Columna("Días de atraso", "entero"),
                Columna("Responsable"),
            ],
            sorted(pendientes, key=lambda f: f[3]),
        ),
    ]
    return resumen, tablas


# --- 3. Correctivos y novedades ------------------------------------------------------------


async def _correctivos(
    db: AsyncSession, actor: Actor, ctx: Contexto, desde: date, hasta: date
) -> tuple[list[tuple[str, str]], list[Tabla]]:
    activos = await _activos(db)
    novedades = [
        n
        for n in await db.scalars(select(Novedad).order_by(Novedad.fecha_reporte))
        if desde <= _local(n.fecha_reporte) <= hasta
    ]
    mtos = list(
        await db.scalars(
            select(MantenimientoEjecutado)
            .where(
                MantenimientoEjecutado.tipo == TipoMantenimiento.CORRECTIVO,
                MantenimientoEjecutado.fecha_ejecucion >= desde,
                MantenimientoEjecutado.fecha_ejecucion <= hasta,
                MantenimientoEjecutado.anulado_at.is_(None),
            )
            .order_by(MantenimientoEjecutado.fecha_ejecucion)
        )
    )
    costo_por_novedad: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    for m in await db.scalars(
        select(MantenimientoEjecutado).where(
            MantenimientoEjecutado.novedad_id.is_not(None), MantenimientoEjecutado.anulado_at.is_(None)
        )
    ):
        costo_por_novedad[m.novedad_id] += m.costo_total  # type: ignore[index]
    filas_n = []
    respuestas, cierres = [], []
    for n in novedades:
        a = activos[n.activo_id]
        resp = _horas(n.fecha_reporte, n.fecha_atencion)
        cierre = (
            Decimal((n.cerrada_at - n.fecha_reporte).total_seconds() / 86400).quantize(Decimal("0.1"))
            if n.cerrada_at
            else None
        )
        if resp is not None:
            respuestas.append(resp)
        if cierre is not None and n.estado == EstadoNovedad.CERRADA:
            cierres.append(cierre)
        fila = [
            n.codigo,
            n.fecha_reporte,
            a.nombre,
            n.prioridad.value.capitalize(),
            n.estado.value.replace("_", " ").capitalize(),
            resp,
            cierre,
            n.descripcion,
        ]
        if ctx.costos:
            fila.insert(7, costo_por_novedad.get(n.id) or n.costo_reparacion)
        filas_n.append(fila)
    col_n = [
        Columna("Código"),
        Columna("Reportada", "fechahora"),
        Columna("Activo"),
        Columna("Prioridad"),
        Columna("Estado"),
        Columna("Respuesta (h)"),
        Columna("Cierre (días)"),
        Columna("Descripción"),
    ]
    if ctx.costos:
        col_n.insert(7, Columna("Costo", "dinero"))
    filas_m = []
    for m in mtos:
        fila = [
            m.codigo,
            m.fecha_ejecucion,
            activos[m.activo_id].nombre,
            ctx.contratistas.get(m.contratista_id, "Personal interno") if m.contratista_id else "Personal interno",
            m.actividades_realizadas,
        ]
        if ctx.costos:
            fila.append(m.costo_total)
        filas_m.append(fila)
    col_m = [Columna("Código"), Columna("Fecha", "fecha"), Columna("Activo"), Columna("Ejecutó"), Columna("Trabajo")]
    if ctx.costos:
        col_m.append(Columna("Costo", "dinero"))

    def prom(xs: list[Decimal]) -> Decimal | None:
        return (sum(xs, Decimal(0)) / len(xs)).quantize(Decimal("0.1")) if xs else None

    resumen = [
        ("Novedades reportadas", str(len(novedades))),
        ("Cerradas", str(sum(n.estado == EstadoNovedad.CERRADA for n in novedades))),
        ("Abiertas", str(sum(n.estado in NOVEDAD_ABIERTA for n in novedades))),
        ("Tiempo medio de respuesta", f"{prom(respuestas)} h".replace(".", ",") if respuestas else "—"),
        ("Tiempo medio de cierre", f"{prom(cierres)} días".replace(".", ",") if cierres else "—"),
        ("Mantenimientos correctivos", str(len(mtos))),
    ]
    if ctx.costos:
        resumen.append(("Costo de los correctivos", pesos(sum((m.costo_total for m in mtos), Decimal(0)))))
    totales_m = None
    if ctx.costos and filas_m:
        totales_m = ["Total", None, "", "", "", sum((m.costo_total for m in mtos), Decimal(0))]
    return resumen, [
        Tabla(
            "Novedades",
            col_n,
            filas_n,
            nota="Respuesta: del reporte a la primera atención. Cierre: del reporte al cierre.",
        ),
        Tabla("Mantenimientos correctivos", col_m, filas_m, totales=totales_m),
    ]


# --- 4. Recomendaciones ----------------------------------------------------------------------


async def _recomendaciones(
    db: AsyncSession, actor: Actor, ctx: Contexto, desde: date, hasta: date
) -> tuple[list[tuple[str, str]], list[Tabla]]:
    recs = await consultas.listar_recomendaciones(db, actor)
    estados = {
        "PENDIENTE": "Pendiente",
        "EN_PROCESO": "En proceso",
        "EJECUTADA": "Ejecutada",
        "DESCARTADA_CON_JUSTIFICACION": "Descartada",
    }
    orden = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}
    recs = sorted(
        recs,
        key=lambda r: (
            r.estado.value not in ("PENDIENTE", "EN_PROCESO"),
            orden[r.prioridad.value],
            r.fecha_limite or date.max,
        ),
    )
    filas = []
    for r in recs:
        fila: list[Any] = [
            r.activo_codigo,
            r.activo.nombre,
            r.descripcion,
            r.prioridad.value.capitalize(),
            estados[r.estado.value],
            _n(r.responsable.nombre) if r.responsable else "",
            r.fecha_limite,
            "Sí" if r.vencida else "",
            r.mantenimiento_origen.nombre if r.mantenimiento_origen else "Administración",
        ]
        if ctx.costos:
            fila.insert(8, r.costo_estimado)
        filas.append(fila)
    columnas = [
        Columna("Código"),
        Columna("Activo"),
        Columna("Recomendación"),
        Columna("Prioridad"),
        Columna("Estado"),
        Columna("Responsable"),
        Columna("Fecha límite", "fecha"),
        Columna("Vencida"),
        Columna("Origen"),
    ]
    if ctx.costos:
        columnas.insert(8, Columna("Costo estimado", "dinero"))
    abiertas = [r for r in recs if r.estado.value in ("PENDIENTE", "EN_PROCESO")]
    resumen = [
        ("Recomendaciones abiertas", str(len(abiertas))),
        ("De prioridad alta", str(sum(r.prioridad.value == "ALTA" for r in abiertas))),
        ("Vencidas", str(sum(r.vencida for r in abiertas))),
        ("Ejecutadas", str(sum(r.estado.value == "EJECUTADA" for r in recs))),
        ("Descartadas con justificación", str(sum(r.estado.value == "DESCARTADA_CON_JUSTIFICACION" for r in recs))),
    ]
    if ctx.costos:
        resumen.append(
            (
                "Costo estimado de las abiertas",
                pesos(sum((r.costo_estimado or Decimal(0) for r in abiertas), Decimal(0))),
            )
        )
    return resumen, [Tabla("Recomendaciones", columnas, filas)]


# --- 5. Costos y proyección ------------------------------------------------------------------


async def proyeccion_detalle(
    db: AsyncSession, ctx: Contexto
) -> tuple[list[list[Any]], list[list[Any]], list[list[Any]]]:
    """Mismo cálculo que resumen_mantenimiento (migración 0006), partida por partida."""
    hoy = ctx.hoy
    activos = await _activos(db)
    vigentes = {i for i, a in activos.items() if a.estado != EstadoActivo.DADO_DE_BAJA}
    contratos = [
        c
        for c in await db.scalars(select(Contratista).order_by(Contratista.razon_social))
        if c.activo
        and c.valor_contrato is not None
        and (c.vigencia_contrato_fin is None or c.vigencia_contrato_fin >= hoy)
    ]
    con_contrato = {c.id for c in contratos}
    plan = []
    for p in await db.scalars(select(PlanPreventivo).order_by(PlanPreventivo.created_at)):
        if (
            not (p.activo and p.aprobado_at and p.costo_estimado is not None and p.activo_id in vigentes)
            or p.contratista_id in con_contrato
        ):
            continue
        if p.periodicidad == Periodicidad.POR_HORAS_USO:
            # Por horas de uso: tantas veces como se ejecutó en el último año (mínimo una)
            ejecutadas = await db.scalar(
                select(func.count())
                .select_from(MantenimientoEjecutado)
                .join(ActividadProgramada, ActividadProgramada.id == MantenimientoEjecutado.actividad_id)
                .where(
                    ActividadProgramada.plan_id == p.id,
                    MantenimientoEjecutado.anulado_at.is_(None),
                    MantenimientoEjecutado.fecha_ejecucion > hoy - timedelta(days=365),
                )
            )
            veces = max(1, int(ejecutadas or 0))
        else:
            veces = VECES_AL_ANIO[p.periodicidad]
        a = activos[p.activo_id]
        plan.append(
            [
                a.codigo_interno,
                a.nombre,
                p.nombre,
                PERIODICIDAD_TXT[p.periodicidad],
                veces,
                p.costo_estimado,
                p.costo_estimado * veces,
            ]
        )
    recs = []
    for r in await db.scalars(
        select(RecomendacionTecnica).where(RecomendacionTecnica.estado.in_(["PENDIENTE", "EN_PROCESO"]))
    ):
        if r.activo_id in vigentes and r.costo_estimado:
            peso = PESO_PRIORIDAD[r.prioridad.value]
            recs.append(
                [
                    activos[r.activo_id].nombre,
                    r.descripcion,
                    r.prioridad.value.capitalize(),
                    r.costo_estimado,
                    int(peso * 100),
                    (r.costo_estimado * peso),
                ]
            )
    filas_contratos = [[c.razon_social, c.vigencia_contrato_fin, c.valor_contrato] for c in contratos]
    return plan, recs, filas_contratos


async def _costos(
    db: AsyncSession, actor: Actor, ctx: Contexto, desde: date, hasta: date
) -> tuple[list[tuple[str, str]], list[Tabla]]:
    activos = await _activos(db)
    mtos = list(
        await db.scalars(
            select(MantenimientoEjecutado).where(
                MantenimientoEjecutado.fecha_ejecucion >= desde,
                MantenimientoEjecutado.fecha_ejecucion <= hasta,
                MantenimientoEjecutado.anulado_at.is_(None),
            )
        )
    )
    total = sum((m.costo_total for m in mtos), Decimal(0))
    correctivo = sum((m.costo_total for m in mtos if m.tipo == TipoMantenimiento.CORRECTIVO), Decimal(0))
    preventivo = total - correctivo

    def agrupar(clave) -> list[list[Any]]:  # type: ignore[no-untyped-def]
        g: dict[str, list[Any]] = defaultdict(lambda: [0, Decimal(0), Decimal(0)])
        for m in mtos:
            fila = g[clave(m)]
            fila[0] += 1
            fila[1 if m.tipo != TipoMantenimiento.CORRECTIVO else 2] += m.costo_total
        return [[k, v[0], v[1], v[2], v[1] + v[2]] for k, v in sorted(g.items(), key=lambda kv: -(kv[1][1] + kv[1][2]))]

    def cols(primera: str) -> list[Columna]:
        return [
            Columna(primera),
            Columna("Intervenciones", "entero"),
            Columna("Preventivo", "dinero"),
            Columna("Correctivo", "dinero"),
            Columna("Total", "dinero"),
        ]

    def tot(filas: list[list[Any]]) -> list[Any]:
        return [
            "Total",
            sum(f[1] for f in filas),
            sum(f[2] for f in filas),
            sum(f[3] for f in filas),
            sum(f[4] for f in filas),
        ]

    por_activo = agrupar(lambda m: f"{activos[m.activo_id].codigo_interno} {activos[m.activo_id].nombre}")
    por_categoria = agrupar(lambda m: ctx.categorias.get(activos[m.activo_id].categoria_id, ""))
    por_contratista = agrupar(
        lambda m: ctx.contratistas.get(m.contratista_id, "Personal interno") if m.contratista_id else "Personal interno"
    )
    por_mes = sorted(agrupar(lambda m: f"{m.fecha_ejecucion.year}-{m.fecha_ejecucion.month:02d}"), key=lambda f: f[0])
    for f in por_mes:
        y, mm = f[0].split("-")
        f[0] = f"{MESES[int(mm) - 1]} {y}"

    anio = hasta.year
    resumen_sql = await panel.resumen(db, anio, hasta.month)
    proy = resumen_sql["proyeccion"]
    plan, recs, contratos = await proyeccion_detalle(db, ctx)
    resumen = [
        ("Costo total del periodo", pesos(total)),
        ("Preventivo", pesos(preventivo)),
        ("Correctivo", pesos(correctivo)),
        ("Proporción correctiva", _txt_porc(_porc(correctivo, total))),
        (f"Proyección {proy['anio']}: plan preventivo", pesos(Decimal(str(proy["plan"])))),
        (f"Proyección {proy['anio']}: recomendaciones (ponderadas)", pesos(Decimal(str(proy["recomendaciones"])))),
        (f"Proyección {proy['anio']}: contratos anuales", pesos(Decimal(str(proy["contratos"])))),
        (f"Proyección {proy['anio']}: total", pesos(Decimal(str(proy["total"])))),
    ]
    tablas = [
        Tabla("Por activo", cols("Activo"), por_activo, totales=tot(por_activo)),
        Tabla("Por categoría", cols("Categoría"), por_categoria, totales=tot(por_categoria)),
        Tabla("Por contratista", cols("Ejecutó"), por_contratista, totales=tot(por_contratista)),
        Tabla("Por mes", cols("Mes"), por_mes, totales=tot(por_mes)),
        Tabla(
            f"Proyección {proy['anio']}: plan preventivo",
            [
                Columna("Código"),
                Columna("Activo"),
                Columna("Plan"),
                Columna("Periodicidad"),
                Columna("Veces al año", "entero"),
                Columna("Costo por vez", "dinero"),
                Columna("Costo anual", "dinero"),
            ],
            plan,
            totales=["Total", "", "", "", None, None, sum((f[6] for f in plan), Decimal(0))],
            nota="Los planes de contratistas con contrato anual vigente no se suman aquí: ya están en el valor del contrato. Por horas de uso: las ejecuciones del último año.",
        ),
        Tabla(
            f"Proyección {proy['anio']}: recomendaciones pendientes",
            [
                Columna("Activo"),
                Columna("Recomendación"),
                Columna("Prioridad"),
                Columna("Costo estimado", "dinero"),
                Columna("Peso (%)", "entero"),
                Columna("Proyectado", "dinero"),
            ],
            recs,
            totales=[
                "Total",
                "",
                "",
                sum((f[3] for f in recs), Decimal(0)),
                None,
                sum((f[5] for f in recs), Decimal(0)),
            ],
            nota="Ponderadas por la probabilidad de ejecutarse el próximo año: alta 100 %, media 60 %, baja 30 %.",
        ),
        Tabla(
            f"Proyección {proy['anio']}: contratos anuales",
            [Columna("Contratista"), Columna("Vence", "fecha"), Columna("Valor anual", "dinero")],
            contratos,
            totales=["Total", None, sum((f[2] for f in contratos), Decimal(0))],
        ),
    ]
    return resumen, tablas


# --- 6. Infraestructura ---------------------------------------------------------------------------


async def _infraestructura(
    db: AsyncSession, actor: Actor, ctx: Contexto, desde: date, hasta: date
) -> tuple[list[tuple[str, str]], list[Tabla]]:
    categorias = {c.id for c in await db.scalars(select(CategoriaActivo).where(CategoriaActivo.es_infraestructura))}
    activos = [
        a
        for a in (await _activos(db)).values()
        if a.categoria_id in categorias and a.estado != EstadoActivo.DADO_DE_BAJA
    ]
    ids = [a.id for a in activos]
    ultimo: dict[uuid.UUID, MantenimientoEjecutado] = {}
    for m in await db.scalars(
        select(MantenimientoEjecutado)
        .where(MantenimientoEjecutado.activo_id.in_(ids), MantenimientoEjecutado.anulado_at.is_(None))
        .order_by(MantenimientoEjecutado.fecha_ejecucion)
    ):
        ultimo[m.activo_id] = m
    proximas = await consultas._proximas(db)
    novedades = [
        n
        for n in await db.scalars(
            select(Novedad).where(Novedad.activo_id.in_(ids), Novedad.estado.in_(NOVEDAD_ABIERTA))
        )
    ]
    recs = list(
        await db.scalars(
            select(RecomendacionTecnica).where(
                RecomendacionTecnica.activo_id.in_(ids), RecomendacionTecnica.estado.in_(["PENDIENTE", "EN_PROCESO"])
            )
        )
    )
    filas = []
    for a in activos:
        u = ultimo.get(a.id)
        color, prox = proximas.get(a.id, (None, None))
        fila: list[Any] = [
            a.codigo_interno,
            a.nombre,
            a.ubicacion,
            ESTADO_TXT[a.estado],
            u.fecha_ejecucion if u else None,
            TIPO_TXT[u.tipo] if u else "",
            prox,
            {"VERDE": "Al día", "AMARILLO": "Próximo", "ROJO": "Vencido"}.get(color or "", "Sin plan"),
            sum(n.activo_id == a.id for n in novedades),
            sum(r.activo_id == a.id for r in recs),
        ]
        if ctx.costos:
            fila.append(sum((r.costo_estimado or Decimal(0) for r in recs if r.activo_id == a.id), Decimal(0)))
        filas.append(fila)
    columnas = [
        Columna("Código"),
        Columna("Elemento"),
        Columna("Ubicación"),
        Columna("Estado"),
        Columna("Última intervención", "fecha"),
        Columna("Tipo"),
        Columna("Próxima", "fecha"),
        Columna("Plan"),
        Columna("Novedades abiertas", "entero"),
        Columna("Recomendaciones", "entero"),
    ]
    if ctx.costos:
        columnas.append(Columna("Inversión recomendada", "dinero"))
    nombres = {a.id: a.nombre for a in activos}
    detalle_n = [
        [
            n.codigo,
            nombres[n.activo_id],
            n.prioridad.value.capitalize(),
            n.estado.value.replace("_", " ").capitalize(),
            n.descripcion,
        ]
        for n in novedades
    ]
    detalle_r = []
    for r in sorted(recs, key=lambda r: {"ALTA": 0, "MEDIA": 1, "BAJA": 2}[r.prioridad.value]):
        fila = [nombres[r.activo_id], r.descripcion, r.prioridad.value.capitalize(), r.fecha_limite]
        if ctx.costos:
            fila.append(r.costo_estimado)
        detalle_r.append(fila)
    col_r = [Columna("Elemento"), Columna("Recomendación"), Columna("Prioridad"), Columna("Fecha límite", "fecha")]
    if ctx.costos:
        col_r.append(Columna("Costo estimado", "dinero"))
    resumen = [
        ("Elementos de infraestructura y redes", str(len(activos))),
        ("Con novedades abiertas", str(len({n.activo_id for n in novedades}))),
        ("Recomendaciones pendientes", str(len(recs))),
    ]
    if ctx.costos:
        resumen.append(
            ("Inversión recomendada pendiente", pesos(sum((r.costo_estimado or Decimal(0) for r in recs), Decimal(0))))
        )
    return resumen, [
        Tabla(
            "Elementos",
            columnas,
            filas,
            nota="Fachadas, cubiertas, impermeabilizaciones, tanques y redes (categorías de infraestructura).",
        ),
        Tabla(
            "Novedades abiertas",
            [Columna("Código"), Columna("Elemento"), Columna("Prioridad"), Columna("Estado"), Columna("Descripción")],
            detalle_n,
        ),
        Tabla("Recomendaciones pendientes", col_r, detalle_r),
    ]


_CONSTRUCTORES = {
    "inventario": _inventario,
    "cumplimiento": _cumplimiento,
    "correctivos": _correctivos,
    "recomendaciones": _recomendaciones,
    "costos": _costos,
    "infraestructura": _infraestructura,
}


def anio_en_curso() -> tuple[date, date]:
    hoy = hoy_bogota()
    return date(hoy.year, 1, 1), hoy


async def _copropiedad(db: AsyncSession, tenant_id: uuid.UUID) -> tuple[str, str]:
    fila = (await db.execute(select(Tenant.name, Tenant.slug).where(Tenant.id == tenant_id))).one()
    return fila[0], fila[1]


async def generar(db: AsyncSession, actor: Actor, tipo: str, desde: date | None, hasta: date | None) -> ReporteActivos:
    if tipo not in _CONSTRUCTORES:
        raise ValidacionError(f"Tipo de informe desconocido: {tipo}")
    exigir(actor, PERMISOS[tipo], f"generar el informe «{TITULOS[tipo]}»")
    ctx = await consultas.contexto(db, actor)
    if tipo in CON_PERIODO:
        if desde is None or hasta is None:
            desde, hasta = anio_en_curso()
        if hasta < desde:
            raise ValidacionError("La fecha final es anterior a la inicial")
        if (hasta - desde).days > 400:
            raise ValidacionError("El periodo máximo de un informe es de un año")
    else:
        desde = hasta = ctx.hoy
    resumen, tablas = await _CONSTRUCTORES[tipo](db, actor, ctx, desde, hasta)
    nombre, _ = await _copropiedad(db, actor.tenant_id)
    return ReporteActivos(
        tipo=tipo,
        titulo=TITULOS[tipo],
        copropiedad=nombre,
        desde=desde,
        hasta=hasta,
        generado=datetime.now(UTC).astimezone(TZ),
        resumen=resumen,
        tablas=tablas,
        corte=tipo not in CON_PERIODO,
    )


# --- 7. Dossier: hoja de vida individual ---------------------------------------------------------


async def dossier(db: AsyncSession, actor: Actor, activo_id: uuid.UUID) -> tuple[ReporteActivos, str]:
    """Hoja de vida completa de un activo. Devuelve el reporte y la URL de su QR."""
    exigir(actor, PERMISOS["dossier"], "descargar la hoja de vida")
    nombre, slug = await _copropiedad(db, actor.tenant_id)
    d = await consultas.detalle_activo(db, actor, activo_id, tenant_slug=slug)
    resumen = [
        ("Código", d.codigo_interno),
        ("Categoría", f"{d.categoria.nombre}{f' · {d.subtipo}' if d.subtipo else ''}"),
        ("Ubicación", d.ubicacion),
        ("Estado", ESTADO_TXT[d.estado]),
        ("Criticidad", d.criticidad.value.capitalize()),
        ("Marca y modelo", " ".join(x for x in (d.marca, d.modelo) if x) or "—"),
        ("Fabricante", d.fabricante or "—"),
        ("Serie", d.numero_serie or "—"),
        ("Instalación", d.fecha_instalacion.strftime("%d/%m/%Y") if d.fecha_instalacion else "—"),
        (
            "Vida útil",
            f"{d.vida_util_anios} años · {d.vida_util_consumida} % consumida".replace(".", ",")
            if d.vida_util_anios and d.vida_util_consumida is not None
            else "—",
        ),
        (
            "Garantía",
            (f"{'Vigente hasta' if d.garantia_vigente else 'Venció el'} {d.fecha_vencimiento_garantia:%d/%m/%Y}")
            if d.fecha_vencimiento_garantia
            else "—",
        ),
        ("Mantenimiento a cargo de", d.mantenedor.nombre if d.mantenedor else "Personal interno"),
    ]
    if d.estado == EstadoActivo.DADO_DE_BAJA:
        resumen.append(
            ("Dado de baja", f"{d.fecha_baja:%d/%m/%Y} · {d.motivo_baja}" if d.fecha_baja else d.motivo_baja or "")
        )
    if d.puede_ver_costos:
        resumen.append(("Costo acumulado de mantenimiento", pesos(d.costo_acumulado or Decimal(0))))
    vigentes = [m for m in d.mantenimientos if not m.anulado]
    historial_cols = [
        Columna("Código"),
        Columna("Fecha", "fecha"),
        Columna("Tipo"),
        Columna("Técnico"),
        Columna("Ejecutó"),
        Columna("Estado posterior"),
    ]
    historial = [
        [
            m.codigo,
            m.fecha_ejecucion,
            TIPO_TXT[m.tipo],
            m.nombre_tecnico,
            m.contratista.nombre if m.contratista else "Personal interno",
            ESTADO_TXT[m.estado_post_intervencion],
        ]
        for m in vigentes
    ]
    if d.puede_ver_costos:
        historial_cols.append(Columna("Costo", "dinero"))
        for f, m in zip(historial, vigentes, strict=True):
            f.append(m.costo_total)
    planes = [
        [
            p.nombre,
            PERIODICIDAD_TXT[p.periodicidad]
            if p.periodicidad != Periodicidad.POR_HORAS_USO
            else f"Cada {p.intervalo_horas} h",
            p.contratista.nombre if p.contratista else "Personal interno",
            "Activo" if p.activo_plan and p.aprobado else "Pausado" if p.aprobado else "Por aprobar",
            p.proxima_fecha,
            p.ejecuciones,
        ]
        for p in d.planes
    ]
    tablas = [
        Tabla(
            "Especificaciones técnicas",
            [Columna("Especificación"), Columna("Valor")],
            [[k, str(v)] for k, v in d.especificaciones.items()],
        ),
        Tabla(
            "Planes de mantenimiento",
            [
                Columna("Plan"),
                Columna("Periodicidad"),
                Columna("Ejecuta"),
                Columna("Estado"),
                Columna("Próxima", "fecha"),
                Columna("Ejecutados", "entero"),
            ],
            planes,
        ),
        Tabla(
            "Historial de intervenciones",
            historial_cols,
            historial,
            totales=(
                ["Total", None, "", "", "", "", sum((m.costo_total or Decimal(0) for m in vigentes), Decimal(0))]
                if d.puede_ver_costos and vigentes
                else None
            ),
        ),
        Tabla(
            "Novedades y fallas",
            [
                Columna("Código"),
                Columna("Reportada", "fechahora"),
                Columna("Prioridad"),
                Columna("Estado"),
                Columna("Descripción"),
            ],
            [
                [
                    n.codigo,
                    n.fecha_reporte,
                    n.prioridad.value.capitalize(),
                    n.estado.value.replace("_", " ").capitalize(),
                    n.descripcion,
                ]
                for n in d.novedades
            ],
        ),
        Tabla(
            "Recomendaciones técnicas",
            [Columna("Recomendación"), Columna("Prioridad"), Columna("Estado"), Columna("Fecha límite", "fecha")],
            [
                [
                    r.descripcion,
                    r.prioridad.value.capitalize(),
                    r.estado.value.replace("_", " ").capitalize().replace("con justificacion", "con justificación"),
                    r.fecha_limite,
                ]
                for r in d.recomendaciones
            ],
        ),
        Tabla(
            "Documentos vinculados",
            [Columna("Documento"), Columna("Tipo"), Columna("Fecha", "fecha")],
            [[x.titulo, x.tipo.value.replace("_", " ").capitalize(), x.fecha_documento] for x in d.documentos],
        ),
    ]
    if d.puede_ver_costos and vigentes:
        por_anio: dict[int, Decimal] = defaultdict(Decimal)
        for m in vigentes:
            por_anio[m.fecha_ejecucion.year] += m.costo_total or Decimal(0)
        tablas.append(
            Tabla(
                "Costos por año",
                [Columna("Año"), Columna("Costo", "dinero")],
                [[str(y), v] for y, v in sorted(por_anio.items())],
                totales=["Total", sum(por_anio.values(), Decimal(0))],
            )
        )
    hoy = hoy_bogota()
    r = ReporteActivos(
        tipo="dossier",
        titulo=f"Hoja de vida · {d.codigo_interno} {d.nombre}",
        copropiedad=nombre,
        desde=hoy,
        hasta=hoy,
        generado=datetime.now(UTC).astimezone(TZ),
        resumen=resumen,
        tablas=tablas,
        corte=True,
    )
    return r, d.qr_url


def dossier_pdf(r: ReporteActivos, qr_url: str) -> bytes:
    """PDF del dossier con el QR del activo en la esquina superior derecha de la primera página."""
    doc = pymupdf.open("pdf", a_pdf(r))
    pagina = doc[0]
    lado = 78
    rect = pymupdf.Rect(pagina.rect.width - 36 - lado, 44, pagina.rect.width - 36, 44 + lado)
    pagina.insert_image(rect, stream=qr.png(qr_url, escala=6))
    pagina.insert_text((rect.x0 + 6, rect.y1 + 9), "Escanee para ver el equipo", fontsize=6, color=(0.4, 0.44, 0.52))
    salida = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return salida
