"""Usuarios de una copropiedad (solo el administrador): invitar, reenviar, cambiar rol y retirar."""

import uuid

from fastapi import APIRouter, Request, status

from app.api.deps import AdminCtx, CurrentUser, DbSession
from app.core.rate_limit import INVITES_PER_USER, enforce
from app.schemas.cuentas import CambioRolIn, InvitacionIn, InvitacionOut, UsuarioCopropiedad
from app.services.cuentas import usuarios
from app.services.notifications.email import email_enabled
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/tenants/{tenant_id}/usuarios", tags=["usuarios"])
CORREO_TASK = "cuentas.correo"


@router.get("", response_model=list[UsuarioCopropiedad])
async def listar(ctx: AdminCtx, db: DbSession) -> list[UsuarioCopropiedad]:
    return await usuarios.listar(db, ctx)


@router.post("", response_model=InvitacionOut, status_code=status.HTTP_201_CREATED)
async def invitar(
    body: InvitacionIn, ctx: AdminCtx, user: CurrentUser, db: DbSession, request: Request
) -> InvitacionOut:
    await enforce(request, INVITES_PER_USER, str(ctx.user_id))
    fila, nuevo, correo = await usuarios.invitar(db, ctx, body, invita=user.full_name)
    await db.commit()
    celery_app.send_task(CORREO_TASK, args=usuarios.correo_a_tarea(correo))
    return InvitacionOut(usuario=fila, nuevo=nuevo, correo_enviado=email_enabled())


@router.post("/{user_id}/reenviar", status_code=status.HTTP_202_ACCEPTED)
async def reenviar(
    user_id: uuid.UUID, ctx: AdminCtx, user: CurrentUser, db: DbSession, request: Request
) -> dict[str, bool]:
    await enforce(request, INVITES_PER_USER, str(ctx.user_id))
    correo = await usuarios.reenviar(db, ctx, user_id, invita=user.full_name)
    await db.commit()
    celery_app.send_task(CORREO_TASK, args=usuarios.correo_a_tarea(correo))
    return {"correo_enviado": email_enabled()}


@router.patch("/{user_id}", response_model=UsuarioCopropiedad)
async def cambiar_rol(user_id: uuid.UUID, body: CambioRolIn, ctx: AdminCtx, db: DbSession) -> UsuarioCopropiedad:
    fila = await usuarios.cambiar_rol(db, ctx, user_id, body.rol)
    await db.commit()
    return fila


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def retirar(user_id: uuid.UUID, ctx: AdminCtx, db: DbSession) -> None:
    await usuarios.retirar(db, ctx, user_id)
    await db.commit()
