"""Panel del dueño de la plataforma: copropiedades y su primer administrador.

Responde 404 a quien no es dueño (no revela que el panel existe).
"""

import uuid
from datetime import UTC, datetime, timedelta

import sentry_sdk
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool

from app.api.deps import DbSession, PlatformAdmin
from app.core.config import get_settings
from app.core.rate_limit import BACKUPS_PER_USER, INVITES_PER_USER, enforce
from app.schemas.cuentas import (
    CopropiedadCreada,
    CopropiedadIn,
    CopropiedadOut,
    CopropiedadUpdate,
    DescargaRespaldoIn,
    EliminarCopropiedadIn,
    EnlaceInvitacion,
    RespaldoOut,
    RespaldosOut,
)
from app.services import respaldos
from app.services.cuentas import plataforma, usuarios
from app.services.notifications.email import email_enabled
from app.services.storage.s3 import get_storage
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/plataforma", tags=["plataforma"])
CORREO_TASK = "cuentas.correo"
RESPALDO_TASK = "respaldos.diario"


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


# --- Respaldos de la base de datos --------------------------------------------------------------------------
@router.get("/respaldos", response_model=RespaldosOut)
async def listar_respaldos(_: PlatformAdmin) -> RespaldosOut:
    lista = await run_in_threadpool(respaldos.listar)
    diarios = [r for r in lista if r.tipo == "diario"]
    ultimo = diarios[0].fecha if diarios else None
    return RespaldosOut(
        respaldos=[RespaldoOut(clave=r.clave, tipo=r.tipo, tamano_bytes=r.tamano, fecha=r.fecha) for r in lista[:60]],  # type: ignore[arg-type]
        ultimo=ultimo,
        al_dia=bool(ultimo and datetime.now(UTC) - ultimo < timedelta(hours=36)),
    )


@router.post("/respaldos", status_code=status.HTTP_202_ACCEPTED)
async def respaldar_ahora(dueno: PlatformAdmin, request: Request) -> dict[str, str]:
    """Encola un respaldo inmediato (tarda uno o dos minutos; aparece en la lista al terminar)."""
    await enforce(request, BACKUPS_PER_USER, str(dueno.id))
    celery_app.send_task(RESPALDO_TASK, kwargs={"forzar": True})
    return {"detail": "Respaldo en curso: aparecerá en la lista en uno o dos minutos."}


@router.post("/respaldos/descargar")
async def descargar_respaldo(body: DescargaRespaldoIn, _: PlatformAdmin) -> dict[str, str]:
    """Enlace firmado de 5 minutos. POST para que la clave no quede en los registros de acceso."""
    if not respaldos.es_clave_valida(body.clave):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Respaldo no encontrado")
    storage = get_storage()
    if await run_in_threadpool(storage.object_size, body.clave) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Respaldo no encontrado")
    nombre = body.clave.rsplit("/", 1)[-1]
    return {"url": storage.presign_get(body.clave, nombre, "application/octet-stream")}


class AlertaDePrueba(RuntimeError):
    """Error intencional para comprobar que las alertas de errores (Sentry) llegan."""


@router.post("/probar-alerta", status_code=status.HTTP_202_ACCEPTED)
async def probar_alerta(dueno: PlatformAdmin, request: Request) -> dict[str, object]:
    """Envía a Sentry un error de prueba (sin datos personales) y responde si las alertas están activas."""
    await enforce(request, BACKUPS_PER_USER, str(dueno.id))
    if not get_settings().sentry_dsn:
        return {"activas": False, "detail": "Las alertas no están activas: falta SENTRY_DSN en el servidor."}
    # Huella única por clic: cada prueba es un «error nuevo» y dispara la regla de alerta (si no, Sentry la agrupa con
    # la anterior y no vuelve a avisar)
    with sentry_sdk.new_scope() as scope:
        scope.fingerprint = ["alerta-de-prueba", uuid.uuid4().hex]
        sentry_sdk.capture_exception(AlertaDePrueba("Alerta de prueba enviada desde el panel de la plataforma"))
    await run_in_threadpool(sentry_sdk.flush, 5)
    return {"activas": True, "detail": "Alerta de prueba enviada: llegará a su correo de Sentry en unos minutos."}
