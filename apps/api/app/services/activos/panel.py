"""Panel gerencial del módulo de mantenimiento (docs/MANTENIMIENTO.md §5).

Las cifras salen de la función resumen_mantenimiento (migración 0006): una sola
fuente para todos los roles, y la única vía del Consejo, que no puede leer el
detalle. Al personal se le agregan las listas accionables (vencidas, novedades
urgentes, recomendaciones altas), que pasan por RLS como cualquier consulta.
"""

import json
import uuid
from datetime import date
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Activo
from app.models.enums import EstadoActividad, PrioridadNovedad, UserRole
from app.services.activos import consultas
from app.services.activos.dominio import PUEDE_VER, PUEDE_VER_COSTOS, vida_util_consumida
from app.services.comun import Actor, exigir, hoy_bogota

PUEDE_VER_PANEL = PUEDE_VER | {UserRole.CONSEJO}


async def resumen(
    db: AsyncSession, anio: int, mes: int, categoria_id: uuid.UUID | None = None, ubicacion: str | None = None
) -> dict[str, Any]:
    fila = await db.scalar(
        text("SELECT resumen_mantenimiento(:a, :m, CAST(:c AS uuid), :u)"),
        {"a": anio, "m": mes, "c": str(categoria_id) if categoria_id else None, "u": ubicacion},
    )
    return fila if isinstance(fila, dict) else json.loads(fila)


def _sin_costos(r: dict[str, Any]) -> dict[str, Any]:
    """Auxiliar y técnico ven el panel operativo, sin cifras de dinero."""
    r = dict(r)
    r["costos"] = None
    r["proyeccion"] = None
    r["recomendaciones"] = {k: v for k, v in r["recomendaciones"].items() if k != "costo_pendiente"}
    return r


async def panel(
    db: AsyncSession,
    actor: Actor,
    anio: int,
    mes: int,
    categoria_id: uuid.UUID | None = None,
    ubicacion: str | None = None,
) -> dict[str, Any]:
    exigir(actor, PUEDE_VER_PANEL, "consultar el panel de mantenimiento")
    datos = await resumen(db, anio, mes, categoria_id, ubicacion)
    if actor.role not in PUEDE_VER_COSTOS | {UserRole.CONSEJO}:
        datos = _sin_costos(datos)
    datos["puede_ver_costos"] = actor.role in PUEDE_VER_COSTOS | {UserRole.CONSEJO}
    datos["detalle"] = None
    if actor.role in PUEDE_VER:  # el Consejo se queda con los consolidados
        datos["detalle"] = await _detalle(db, actor, categoria_id, ubicacion)
    return datos


async def _detalle(
    db: AsyncSession, actor: Actor, categoria_id: uuid.UUID | None, ubicacion: str | None
) -> dict[str, Any]:
    hoy = hoy_bogota()
    filtro = consultas.FiltroActividades(estado=EstadoActividad.PROGRAMADA, hasta=hoy)
    vencidas = [
        x
        for x in await consultas.listar_actividades(db, actor, filtro)
        if x.semaforo == "ROJO" and await _pasa(db, x.activo.id, categoria_id, ubicacion)
    ]
    urgentes = [
        n
        for n in await consultas.listar_novedades(db, actor, abiertas=True)
        if n.prioridad in (PrioridadNovedad.CRITICA, PrioridadNovedad.ALTA)
        and await _pasa(db, n.activo.id, categoria_id, ubicacion)
    ]
    recs = [
        r
        for r in await consultas.listar_recomendaciones(db, actor, pendientes=True)
        if r.prioridad.value == "ALTA" and await _pasa(db, r.activo.id, categoria_id, ubicacion)
    ]
    reemplazo = []
    for a in await db.scalars(select(Activo).where(Activo.estado != "DADO_DE_BAJA").order_by(Activo.consecutivo)):
        consumida = vida_util_consumida(a.fecha_instalacion, a.vida_util_anios, hoy)
        if consumida is not None and consumida >= 90 and await _pasa(db, a.id, categoria_id, ubicacion):
            reemplazo.append(
                {"id": a.id, "codigo": a.codigo_interno, "nombre": a.nombre, "vida_util_consumida": consumida}
            )
    return {
        "vencidas": [x.model_dump(mode="json") for x in vencidas[:10]],
        "novedades_urgentes": [n.model_dump(mode="json") for n in urgentes[:10]],
        "recomendaciones_altas": [r.model_dump(mode="json") for r in recs[:10]],
        "para_reemplazo": [
            {**x, "id": str(x["id"]), "vida_util_consumida": str(x["vida_util_consumida"])} for x in reemplazo
        ],
    }


async def _pasa(db: AsyncSession, activo_id: uuid.UUID, categoria_id: uuid.UUID | None, ubicacion: str | None) -> bool:
    """¿El activo cumple los filtros del panel? (sin filtros, siempre)."""
    if not categoria_id and not (ubicacion and ubicacion.strip()):
        return True
    a = await db.get(Activo, activo_id)
    if a is None:
        return False
    if categoria_id and a.categoria_id != categoria_id:
        return False
    return not (ubicacion and ubicacion.strip().lower() not in a.ubicacion.lower())


def anio_mes(anio: int | None, mes: int | None) -> tuple[int, int]:
    hoy: date = hoy_bogota()
    return anio or hoy.year, mes or hoy.month
