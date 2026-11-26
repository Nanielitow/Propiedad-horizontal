"""Usuarios de una copropiedad: el administrador invita a su equipo y a los residentes, cambia roles y retira accesos.

Una persona tiene UNA cuenta (su correo) y una membresía por copropiedad, con un rol en cada una. Invitar a
alguien que ya tiene cuenta solo le agrega la membresía y le avisa; a quien no la tiene se le crea sin clave y se
le envía un enlace para definirla.
"""

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext
from app.models import Membership, Persona, User
from app.models.enums import UserRole
from app.schemas.cuentas import ETIQUETA_ROL, InvitacionIn, UsuarioCopropiedad
from app.services.cuentas import enlaces
from app.services.cuentas.enlaces import Correo

DEMO_BLOQUEADA = HTTPException(
    status.HTTP_403_FORBIDDEN,
    "En los conjuntos de demostración no se pueden invitar ni modificar usuarios.",
)


def _no_demo(ctx: TenantContext) -> None:
    if ctx.is_demo:
        raise DEMO_BLOQUEADA


def _estado(user: User) -> str:
    if not user.is_active:
        return "DESACTIVADO"
    return "ACTIVO" if user.password_hash else "INVITADO"


def _fila(user: User, m: Membership, ctx: TenantContext) -> UsuarioCopropiedad:
    return UsuarioCopropiedad(
        user_id=user.id,
        nombre=user.full_name,
        email=user.email,
        rol=m.role,
        rol_etiqueta=ETIQUETA_ROL[m.role],
        estado=_estado(user),  # type: ignore[arg-type]
        ultimo_ingreso=user.last_login_at,
        agregado_en=m.created_at,
        es_usted=user.id == ctx.user_id,
    )


async def listar(db: AsyncSession, ctx: TenantContext) -> list[UsuarioCopropiedad]:
    filas = await db.execute(
        select(User, Membership)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.tenant_id == ctx.tenant_id)
        .order_by(Membership.role, func.lower(User.full_name))
    )
    return [_fila(u, m, ctx) for u, m in filas]


async def _membresia(db: AsyncSession, ctx: TenantContext, user_id: uuid.UUID) -> tuple[User, Membership]:
    fila = (
        await db.execute(
            select(User, Membership)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.tenant_id == ctx.tenant_id, Membership.user_id == user_id)
        )
    ).first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese usuario no tiene acceso a esta copropiedad")
    return fila[0], fila[1]


async def _administradores(db: AsyncSession, tenant_id: uuid.UUID) -> int:
    return (
        await db.scalar(
            select(func.count())
            .select_from(Membership)
            .join(User, User.id == Membership.user_id)
            .where(Membership.tenant_id == tenant_id, Membership.role == UserRole.ADMIN, User.is_active)
        )
        or 0
    )


async def invitar(
    db: AsyncSession, ctx: TenantContext, body: InvitacionIn, *, invita: str | None
) -> tuple[UsuarioCopropiedad, bool, Correo]:
    """Da acceso a la copropiedad. Devuelve (usuario, cuenta_nueva, correo a enviar)."""
    _no_demo(ctx)
    user = await db.scalar(select(User).where(User.email == body.email))
    nuevo = user is None
    if user is None:
        user = User(email=body.email, full_name=body.nombre, password_hash=None)
        db.add(user)
        await db.flush()
    elif not user.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esa cuenta está desactivada en la plataforma")
    existe = await db.scalar(
        select(Membership.id).where(Membership.tenant_id == ctx.tenant_id, Membership.user_id == user.id)
    )
    if existe:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{body.email} ya tiene acceso a esta copropiedad")
    m = Membership(tenant_id=ctx.tenant_id, user_id=user.id, role=body.rol)
    db.add(m)
    await db.flush()

    if body.persona_id:
        persona = await db.get(Persona, body.persona_id)
        if persona is None or persona.tenant_id != ctx.tenant_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Persona no encontrada")
        if persona.user_id and persona.user_id != user.id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Esa persona ya está vinculada a otra cuenta")
        persona.user_id = user.id  # el trigger deriva la unidad que verá en el portal
        await db.flush()

    await db.refresh(m)
    copropiedad = await enlaces.nombre_copropiedad(db, ctx.tenant_id) or "la copropiedad"
    if user.password_hash is None:
        url = await enlaces.emitir(db, user, enlaces.INVITACION, tenant_id=ctx.tenant_id, creado_por=ctx.user_id)
        correo = enlaces.correo_invitacion(user, url, copropiedad, invita)
    else:
        correo = enlaces.correo_nuevo_acceso(user, copropiedad, ETIQUETA_ROL[body.rol])
    return _fila(user, m, ctx), nuevo, correo


async def reenviar(db: AsyncSession, ctx: TenantContext, user_id: uuid.UUID, *, invita: str | None) -> Correo:
    _no_demo(ctx)
    user, _ = await _membresia(db, ctx, user_id)
    if user.password_hash is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese usuario ya activó su cuenta")
    url = await enlaces.emitir(db, user, enlaces.INVITACION, tenant_id=ctx.tenant_id, creado_por=ctx.user_id)
    return enlaces.correo_invitacion(user, url, await enlaces.nombre_copropiedad(db, ctx.tenant_id), invita)


async def cambiar_rol(db: AsyncSession, ctx: TenantContext, user_id: uuid.UUID, rol: UserRole) -> UsuarioCopropiedad:
    _no_demo(ctx)
    user, m = await _membresia(db, ctx, user_id)
    if m.role == UserRole.ADMIN and rol != UserRole.ADMIN and await _administradores(db, ctx.tenant_id) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "La copropiedad debe conservar al menos un administrador")
    m.role = rol
    await db.flush()
    return _fila(user, m, ctx)


async def retirar(db: AsyncSession, ctx: TenantContext, user_id: uuid.UUID) -> None:
    """Quita el acceso a ESTA copropiedad (la cuenta sigue existiendo para las demás)."""
    _no_demo(ctx)
    user, m = await _membresia(db, ctx, user_id)
    if m.role == UserRole.ADMIN and await _administradores(db, ctx.tenant_id) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "La copropiedad debe conservar al menos un administrador")
    await db.execute(
        update(Persona).where(Persona.tenant_id == ctx.tenant_id, Persona.user_id == user.id).values(user_id=None)
    )
    await db.delete(m)
    await db.flush()


def correo_a_tarea(c: Correo) -> list[Any]:
    return [c.destino, c.asunto, c.texto, c.html]
