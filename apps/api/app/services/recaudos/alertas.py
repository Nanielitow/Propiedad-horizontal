"""Alertas de auditoría del módulo de recaudos.

Se crean dentro de la misma transacción que las origina (un cierre con
faltante, una consignación descuadrada...): si la operación se revierte, la
alerta también. El correo se envía DESPUÉS del commit con una tarea de Celery
(app.workers.tasks.recaudos), nunca dentro de la transacción.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Select, and_, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AlertaRecaudo, Recaudo
from app.models.enums import EstadoAlerta, EstadoRecaudo, SeveridadAlerta, TipoAlerta
from app.services.recaudos.dominio import (
    PUEDE_ATENDER_ALERTAS,
    PUEDE_VER_ALERTAS,
    Actor,
    NoEncontrado,
    ValidacionError,
    exigir,
    pesos,
)

DIAS_VERIFICACION_POR_DEFECTO = 3


async def crear_alerta(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    tipo: TipoAlerta,
    severidad: SeveridadAlerta,
    entidad: str,
    entidad_id: uuid.UUID,
    mensaje: str,
    monto: Decimal | None = None,
) -> AlertaRecaudo:
    alerta = AlertaRecaudo(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        tipo=tipo,
        severidad=severidad,
        entidad=entidad,
        entidad_id=entidad_id,
        mensaje=mensaje,
        monto=monto,
    )
    db.add(alerta)
    await db.flush()
    return alerta


def _consulta(estado: EstadoAlerta | None) -> Select[tuple[AlertaRecaudo]]:
    q = select(AlertaRecaudo).order_by(AlertaRecaudo.created_at.desc())
    return q.where(AlertaRecaudo.estado == estado) if estado else q


async def listar_alertas(
    db: AsyncSession, actor: Actor, estado: EstadoAlerta | None = EstadoAlerta.ABIERTA, limite: int = 100
) -> list[AlertaRecaudo]:
    exigir(actor, PUEDE_VER_ALERTAS, "consultar alertas")
    return list(await db.scalars(_consulta(estado).limit(limite)))


async def atender_alerta(
    db: AsyncSession, actor: Actor, alerta_id: uuid.UUID, resolucion: str, *, ahora: datetime | None = None
) -> AlertaRecaudo:
    exigir(actor, PUEDE_ATENDER_ALERTAS, "atender alertas")
    alerta = await db.get(AlertaRecaudo, alerta_id)
    if alerta is None or alerta.tenant_id != actor.tenant_id:
        raise NoEncontrado("Alerta no encontrada")
    if alerta.estado == EstadoAlerta.ATENDIDA:
        raise ValidacionError("La alerta ya fue atendida")
    if len(resolucion.strip()) < 5:
        raise ValidacionError("Describa cómo se resolvió la alerta")
    alerta.estado = EstadoAlerta.ATENDIDA
    alerta.atendida_por_id = actor.user_id
    alerta.atendida_at = ahora or datetime.now(UTC)
    alerta.resolucion = resolucion.strip()
    await db.flush()
    return alerta


async def detectar_transferencias_sin_verificar(
    db: AsyncSession, tenant_id: uuid.UUID, *, dias: int = DIAS_VERIFICACION_POR_DEFECTO, ahora: datetime | None = None
) -> list[AlertaRecaudo]:
    """Una alerta por transferencia pendiente hace más de `dias` días (sin duplicar las abiertas).

    Corre como SYSTEM desde la tarea diaria; la sesión ya trae el contexto RLS del tenant.
    """
    limite = (ahora or datetime.now(UTC)) - timedelta(days=dias)
    ya_alertada = exists().where(
        and_(
            AlertaRecaudo.entidad_id == Recaudo.id,
            AlertaRecaudo.tipo == TipoAlerta.TRANSFERENCIA_SIN_VERIFICAR,
            AlertaRecaudo.estado == EstadoAlerta.ABIERTA,
        )
    )
    pendientes = await db.scalars(
        select(Recaudo)
        .where(
            Recaudo.estado == EstadoRecaudo.PENDIENTE_VERIFICACION,
            Recaudo.fecha_recaudo < limite,
            ~ya_alertada,
        )
        .order_by(Recaudo.consecutivo)
    )
    alertas = []
    for r in pendientes:
        alertas.append(
            await crear_alerta(
                db,
                tenant_id,
                tipo=TipoAlerta.TRANSFERENCIA_SIN_VERIFICAR,
                severidad=SeveridadAlerta.ADVERTENCIA,
                entidad="recaudo",
                entidad_id=r.id,
                mensaje=(
                    f"El recaudo #{r.consecutivo} ({r.medio_pago.value.lower()} de {r.nombre_pagador} por "
                    f"{pesos(r.valor_recibido)}) lleva más de {dias} días sin verificarse en el extracto."
                ),
                monto=r.valor_recibido,
            )
        )
    return alertas
