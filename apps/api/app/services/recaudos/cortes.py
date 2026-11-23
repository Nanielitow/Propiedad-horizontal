"""Corte mensual consolidado: la foto del mes para el Consejo de Administración.

Se genera automáticamente el día 1 (tarea de Celery) para el mes anterior, o a
mano por la administración para un mes ya cerrado. Es una FOTO: se genera una
sola vez por mes (único por copropiedad y periodo) y sus archivos quedan en el
almacenamiento; no se recalcula aunque después cambien los datos.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CorteMensual
from app.services.recaudos.dominio import TZ, Actor, R, ValidacionError, exigir
from app.services.recaudos.exportar import a_excel, a_pdf
from app.services.recaudos.reportes import MESES, Reporte, reporte_corte
from app.services.storage.s3 import get_storage

PUEDE_VER_CORTES = frozenset({R.ADMIN, R.CONTABILIDAD, R.CONSEJO})
PUEDE_GENERAR_CORTE = frozenset({R.ADMIN})
PDF = "application/pdf"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class Almacen(Protocol):
    def put_bytes(self, key: str, data: bytes, content_type: str) -> None: ...
    def presign_get(self, key: str, filename: str, content_type: str = ...) -> str: ...


@dataclass
class CorteGenerado:
    corte: CorteMensual
    reporte: Reporte
    pdf: bytes


def nombre_periodo(periodo: date) -> str:
    return f"{MESES[periodo.month - 1]} de {periodo.year}"


def mes_anterior(hoy: date | None = None) -> tuple[int, int]:
    hoy = hoy or datetime.now(TZ).date()
    return (hoy.year - 1, 12) if hoy.month == 1 else (hoy.year, hoy.month - 1)


async def generar_corte(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    anio: int,
    mes: int,
    *,
    almacen: Almacen | None = None,
    hoy: date | None = None,
) -> CorteGenerado:
    """Requiere una sesión con contexto ADMIN o SYSTEM del tenant. No hace commit."""
    periodo = date(anio, mes, 1)
    hoy = hoy or datetime.now(TZ).date()
    if periodo >= hoy.replace(day=1):
        raise ValidacionError("Solo se generan cortes de meses ya cerrados")
    existente = await db.scalar(select(CorteMensual.id).where(CorteMensual.periodo == periodo))
    if existente is not None:
        raise ValidacionError(f"El corte de {nombre_periodo(periodo)} ya existe: los cortes no se regeneran")

    reporte, kpis = await reporte_corte(db, tenant_id, anio, mes)
    pdf, xlsx = a_pdf(reporte), a_excel(reporte)
    base = f"tenants/{tenant_id}/recaudos/cortes/{periodo:%Y-%m}"
    corte = CorteMensual(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        periodo=periodo,
        resumen=kpis,
        pdf_key=f"{base}.pdf",
        xlsx_key=f"{base}.xlsx",
    )
    db.add(corte)
    await db.flush()  # si el periodo ya existiera (carrera), falla aquí, antes de subir archivos
    almacen = almacen or get_storage()
    almacen.put_bytes(f"{base}.pdf", pdf, PDF)
    almacen.put_bytes(f"{base}.xlsx", xlsx, XLSX)
    return CorteGenerado(corte, reporte, pdf)


async def generar_corte_manual(
    db: AsyncSession, actor: Actor, anio: int, mes: int, *, almacen: Almacen | None = None
) -> CorteGenerado:
    exigir(actor, PUEDE_GENERAR_CORTE, "generar cortes mensuales")
    return await generar_corte(db, actor.tenant_id, anio, mes, almacen=almacen)


@dataclass
class CorteVista:
    periodo: date
    nombre: str
    total_mes: str
    cantidad_mes: int
    generado_at: datetime
    pdf_url: str | None
    xlsx_url: str | None
    resumen: dict[str, Any]


async def listar_cortes(db: AsyncSession, actor: Actor, *, almacen: Almacen | None = None) -> list[CorteVista]:
    exigir(actor, PUEDE_VER_CORTES, "consultar los cortes mensuales")
    almacen = almacen or get_storage()
    cortes = await db.scalars(select(CorteMensual).order_by(CorteMensual.periodo.desc()))
    vistas = []
    for c in cortes:
        nombre = f"corte-recaudos-{c.periodo:%Y-%m}"
        vistas.append(
            CorteVista(
                periodo=c.periodo,
                nombre=nombre_periodo(c.periodo),
                total_mes=str(c.resumen.get("total_mes", "0")),
                cantidad_mes=int(c.resumen.get("cantidad_mes", 0)),
                generado_at=c.generado_at,
                pdf_url=almacen.presign_get(c.pdf_key, f"{nombre}.pdf", PDF) if c.pdf_key else None,
                xlsx_url=almacen.presign_get(c.xlsx_key, f"{nombre}.xlsx", XLSX) if c.xlsx_key else None,
                resumen=c.resumen.get("resumen", {}),
            )
        )
    return vistas
