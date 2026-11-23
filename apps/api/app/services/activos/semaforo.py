"""Semáforo de mantenimiento: calculado al consultar (vista v_semaforo_actividades).

Nunca se guarda un color: se desactualizaría a medianoche. La vista aplica la RLS
de quien consulta y usa la fecha de Bogotá.
"""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.activos.dominio import Color, peor_color


@dataclass(frozen=True)
class ActividadSemaforo:
    id: uuid.UUID
    plan_id: uuid.UUID
    activo_id: uuid.UUID
    fecha_programada: date
    dias_restantes: int
    color: Color


_SQL = text(
    "SELECT id, plan_id, activo_id, fecha_programada, dias_restantes, semaforo FROM v_semaforo_actividades"
    " WHERE (CAST(:activo AS uuid) IS NULL OR activo_id = CAST(:activo AS uuid))"
    " ORDER BY fecha_programada"
)


async def actividades(db: AsyncSession, activo_id: uuid.UUID | None = None) -> list[ActividadSemaforo]:
    filas = await db.execute(_SQL, {"activo": str(activo_id) if activo_id else None})
    return [ActividadSemaforo(*fila) for fila in filas]


async def por_activo(db: AsyncSession) -> dict[uuid.UUID, Color]:
    """El color de cada activo es el peor de sus actividades pendientes."""
    colores: dict[uuid.UUID, list[Color]] = {}
    for a in await actividades(db):
        colores.setdefault(a.activo_id, []).append(a.color)
    return {k: c for k, v in colores.items() if (c := peor_color(v)) is not None}
