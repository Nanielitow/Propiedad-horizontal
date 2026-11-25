"""Paz y salvo: se emite solo si la unidad no tiene saldo vencido. Lleva consecutivo y un
código de verificación con el que un tercero (notaría, inmobiliaria) puede comprobarlo."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PazYSalvo, Unit
from app.models.enums import UserRole
from app.services.cartera import comun
from app.services.cartera import dominio as d
from app.services.comun import Actor, NoEncontrado, ValidacionError, exigir, hoy_bogota, pesos


async def emitir(db: AsyncSession, actor: Actor, unidad_id: uuid.UUID) -> PazYSalvo:
    exigir(actor, d.PUEDE_PAZ_Y_SALVO, "expedir paz y salvos")
    u = await db.get(Unit, unidad_id)  # la RLS no le muestra al residente unidades ajenas
    if u is None or u.tenant_id != actor.tenant_id:
        raise NoEncontrado("Unidad no encontrada")
    hoy = hoy_bogota()
    vencido = await comun.saldo_unidad(db, u.id, vencido_a=hoy)
    if vencido > 0:
        quien = "Su unidad tiene" if actor.role == UserRole.RESIDENTE else f"La unidad {u.etiqueta} tiene"
        raise ValidacionError(f"{quien} un saldo vencido de {pesos(vencido)}: no se puede expedir el paz y salvo")
    _, titular = await comun.responsable(db, u.id)
    p = PazYSalvo(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        unidad_id=u.id,
        fecha_emision=hoy,
        valido_hasta=d.fin_de_mes(hoy),
        titular_nombre=titular,
        codigo_verificacion=d.codigo_verificacion(),
        emitido_por_id=actor.user_id,
    )
    db.add(p)
    await db.flush()
    return p


async def verificar(db: AsyncSession, actor: Actor, codigo: str) -> PazYSalvo:
    p = await db.scalar(select(PazYSalvo).where(PazYSalvo.codigo_verificacion == codigo.strip().upper()))
    if p is None or p.tenant_id != actor.tenant_id:
        raise NoEncontrado("No existe un paz y salvo con ese código en esta copropiedad")
    return p
