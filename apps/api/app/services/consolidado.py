"""Panel consolidado: lo que pide atención en cada copropiedad que la persona administra, en una sola vista.

Recorre las membresías con rol ADMIN y, para cada copropiedad, fija el contexto RLS de esa copropiedad y llama a los
mismos cálculos de cada módulo (así las cifras coinciden con las de sus pantallas). Si un módulo falla en una
copropiedad, esa fila muestra el error y las demás siguen.
"""

import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext
from app.db.rls import set_rls_context
from app.models import Deadline, Membership, Tenant
from app.models.enums import DeadlineStatus, EstadoAsamblea, UserRole
from app.services.activos import panel as panel_activos
from app.services.asambleas import consultas as asambleas
from app.services.cartera import consultas as cartera
from app.services.portal import consultas as portal
from app.services.recaudos import consultas as recaudos
from app.services.recaudos.dominio import TZ

log = logging.getLogger(__name__)


class ProximaAsamblea(BaseModel):
    id: uuid.UUID
    titulo: str
    fecha_hora: datetime
    en_curso: bool


class ResumenCopropiedad(BaseModel):
    tenant_id: uuid.UUID
    nombre: str
    slug: str
    is_demo: bool
    # Cartera
    cartera_configurada: bool = False
    cartera_vencida: Decimal = Decimal(0)
    unidades_en_mora: int = 0
    recaudo_pct: Decimal | None = None
    # Atención al residente
    pqrs_abiertas: int = 0
    pqrs_vencidas: int = 0
    reservas_por_decidir: int = 0
    # Mantenimiento
    mantenimientos_vencidos: int = 0
    novedades_criticas: int = 0
    novedades_sin_atender: int = 0
    # Recaudos
    recaudado_mes: Decimal = Decimal(0)
    transferencias_por_verificar: int = 0
    alertas_recaudo: int = 0
    # Vencimientos (pólizas, contratos)
    vencimientos_por_revisar: int = 0
    vencimientos_proximos: int = 0  # confirmados que vencen en 30 días o menos
    vencimientos_vencidos: int = 0
    proxima_asamblea: ProximaAsamblea | None = None
    errores: list[str] = []

    @property
    def alertas(self) -> int:
        return (
            self.pqrs_vencidas
            + self.mantenimientos_vencidos
            + self.novedades_criticas
            + self.alertas_recaudo
            + self.vencimientos_vencidos
        )


class ResumenConsolidado(BaseModel):
    generado: datetime
    copropiedades: list[ResumenCopropiedad]


async def _intentar(fila: ResumenCopropiedad, modulo: str, corrutina) -> object | None:  # type: ignore[no-untyped-def]
    try:
        return await corrutina
    except Exception:  # un módulo no debe tumbar el panel completo
        log.exception("panel consolidado: %s falló en %s", modulo, fila.slug)
        fila.errores.append(modulo)
        return None


async def _vencimientos(db: AsyncSession, hoy_d) -> tuple[int, int, int]:  # type: ignore[no-untyped-def]
    filas = (
        await db.execute(
            select(Deadline.status, Deadline.due_date).where(
                Deadline.status.in_([DeadlineStatus.PENDING_REVIEW, DeadlineStatus.ACTIVE])
            )
        )
    ).all()
    por_revisar = sum(1 for s, _ in filas if s == DeadlineStatus.PENDING_REVIEW)
    activos = [d for s, d in filas if s == DeadlineStatus.ACTIVE and d is not None]
    vencidos = sum(1 for d in activos if d < hoy_d)
    proximos = sum(1 for d in activos if hoy_d <= d <= hoy_d + timedelta(days=30))
    return por_revisar, proximos, vencidos


async def resumen(db: AsyncSession, user_id: uuid.UUID) -> ResumenConsolidado:
    ahora = datetime.now(TZ)
    copropiedades = (
        await db.execute(
            select(Tenant.id, Tenant.name, Tenant.slug, Tenant.is_demo)
            .join(Membership, Membership.tenant_id == Tenant.id)
            .where(Membership.user_id == user_id, Membership.role == UserRole.ADMIN, Tenant.deleted_at.is_(None))
            .order_by(func.lower(Tenant.name))
        )
    ).all()
    salida: list[ResumenCopropiedad] = []
    for tid, nombre, slug, demo in copropiedades:
        await set_rls_context(db, tenant_id=tid, user_id=user_id, role=UserRole.ADMIN.value)
        ctx = TenantContext(tenant_id=tid, user_id=user_id, role=UserRole.ADMIN, is_demo=demo)
        fila = ResumenCopropiedad(tenant_id=tid, nombre=nombre, slug=slug, is_demo=demo)

        c = await _intentar(fila, "cartera", cartera.resumen(db, ctx))
        if c is not None:
            fila.cartera_configurada = c.configurada  # type: ignore[attr-defined]
            fila.cartera_vencida = c.cartera_vencida  # type: ignore[attr-defined]
            fila.unidades_en_mora = c.unidades_en_mora  # type: ignore[attr-defined]
            fila.recaudo_pct = c.recaudo_pct  # type: ignore[attr-defined]

        p = await _intentar(fila, "portal", portal.pendientes_personal(db, ctx))
        if p is not None:
            fila.pqrs_abiertas = p.pqrs_abiertas  # type: ignore[attr-defined]
            fila.pqrs_vencidas = p.pqrs_vencidas  # type: ignore[attr-defined]
            fila.reservas_por_decidir = p.reservas_por_decidir  # type: ignore[attr-defined]

        m = await _intentar(fila, "mantenimiento", panel_activos.resumen(db, ahora.year, ahora.month))
        if isinstance(m, dict):
            fila.mantenimientos_vencidos = int((m.get("semaforo") or {}).get("ROJO", 0))
            novedades = m.get("novedades") or {}
            fila.novedades_criticas = int((novedades.get("abiertas_por_prioridad") or {}).get("CRITICA", 0))
            fila.novedades_sin_atender = int(novedades.get("sin_atender", 0))

        r = await _intentar(fila, "recaudos", recaudos.dashboard(db, ctx, ahora.year, ahora.month))
        if r is not None:
            fila.recaudado_mes = r.total_mes  # type: ignore[attr-defined]
            fila.transferencias_por_verificar = r.transferencias_pendientes.cantidad  # type: ignore[attr-defined]
            fila.alertas_recaudo = r.alertas_abiertas  # type: ignore[attr-defined]

        v = await _intentar(fila, "vencimientos", _vencimientos(db, ahora.date()))
        if isinstance(v, tuple):
            fila.vencimientos_por_revisar, fila.vencimientos_proximos, fila.vencimientos_vencidos = v

        a = await _intentar(fila, "asambleas", asambleas.listar(db, ctx))
        if isinstance(a, list):
            futuras = [
                x
                for x in a
                if x.estado == EstadoAsamblea.EN_CURSO
                or (x.estado == EstadoAsamblea.PROGRAMADA and x.fecha_hora >= ahora - timedelta(hours=12))
            ]
            if futuras:
                x = min(futuras, key=lambda y: (y.estado != EstadoAsamblea.EN_CURSO, y.fecha_hora))
                fila.proxima_asamblea = ProximaAsamblea(
                    id=x.id, titulo=x.titulo, fecha_hora=x.fecha_hora, en_curso=x.estado == EstadoAsamblea.EN_CURSO
                )
        salida.append(fila)
    return ResumenConsolidado(generado=ahora, copropiedades=salida)
