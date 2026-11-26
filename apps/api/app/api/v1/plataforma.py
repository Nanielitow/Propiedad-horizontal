"""Panel del dueño de la plataforma: copropiedades y su primer administrador.

Responde 404 a quien no es dueño (no revela que el panel existe).
"""

import uuid

from fastapi import APIRouter, Request, status

from app.api.deps import DbSession, PlatformAdmin
from app.core.rate_limit import INVITES_PER_USER, enforce
from app.schemas.cuentas import (
    CopropiedadCreada,
    CopropiedadIn,
    CopropiedadOut,
    CopropiedadUpdate,
    EliminarCopropiedadIn,
    EnlaceInvitacion,
)
from app.services.cuentas import plataforma, usuarios
from app.services.notifications.email import email_enabled
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/plataforma", tags=["plataforma"])
CORREO_TASK = "cuentas.correo"


@router.get("/copropiedades", response_model=list[CopropiedadOut])
async def listar(_: PlatformAdmin, db: DbSession) -> list[CopropiedadOut]:
    return await plataforma.listar(db)


@router.post("/copropiedades", response_model=CopropiedadCreada, status_code=status.HTTP_201_CREATED)
async def crear(body: CopropiedadIn, dueno: PlatformAdmin, db: DbSession, request: Request) -> CopropiedadCreada:
    await enforce(request, INVITES_PER_USER, str(dueno.id))
    copropiedad, nuevo, correo = await plataforma.crear(db, dueno, body)
    await db.commit()
    celery_app.send_task(CORREO_TASK, args=usuarios.correo_a_tarea(correo))
    return CopropiedadCreada(
        copropiedad=copropiedad,
        administrador_nuevo=nuevo,
        correo_enviado=email_enabled(),
        enlace_invitacion=correo.enlace,
    )


@router.patch("/copropiedades/{tenant_id}", response_model=CopropiedadOut)
async def actualizar(tenant_id: uuid.UUID, body: CopropiedadUpdate, _: PlatformAdmin, db: DbSession) -> CopropiedadOut:
    out = await plataforma.actualizar(db, tenant_id, body)
    await db.commit()
    return out


@router.post("/copropiedades/{tenant_id}/enlaces", response_model=list[EnlaceInvitacion])
async def enlaces_pendientes(
    tenant_id: uuid.UUID, dueno: PlatformAdmin, db: DbSession, request: Request
) -> list[EnlaceInvitacion]:
    """Enlaces nuevos de activación para enviarlos por otro medio. Anulan los que se enviaron por correo."""
    await enforce(request, INVITES_PER_USER, str(dueno.id))
    salida = await plataforma.enlaces_pendientes(db, dueno, tenant_id)
    await db.commit()
    return salida


@router.post("/copropiedades/{tenant_id}/eliminar", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(tenant_id: uuid.UUID, body: EliminarCopropiedadIn, _: PlatformAdmin, db: DbSession) -> None:
    """Borrado lógico, confirmado con el nombre exacto de la copropiedad."""
    await plataforma.eliminar(db, tenant_id, body.confirmacion)
    await db.commit()
