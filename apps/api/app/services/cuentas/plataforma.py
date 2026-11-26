"""Panel del dueño de la plataforma: crear copropiedades con su primer administrador y editarlas.

El dueño no necesita pertenecer a cada copropiedad: los conteos salen de plataforma_resumen() (SECURITY
DEFINER, solo cifras) y la copropiedad nueva se inicializa con contexto SYSTEM.
"""

import re
import unicodedata
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext
from app.db.rls import set_rls_context
from app.models import AccountToken, Membership, Tenant, User
from app.models.enums import UserRole
from app.schemas.cuentas import (
    CopropiedadIn,
    CopropiedadOut,
    CopropiedadUpdate,
    EnlaceInvitacion,
    InvitacionIn,
)
from app.services.cuentas import enlaces, usuarios
from app.services.cuentas.enlaces import Correo

# Catálogos base de cada módulo (idempotentes)
SEMILLAS = ("seed_conceptos_recaudo", "seed_categorias_activos", "seed_conceptos_cartera")


def slug_de(nombre: str) -> str:
    base = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"\b(conjunto|residencial|edificio|copropiedad|propiedad horizontal|ph)\b", " ", base)
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return (base or "copropiedad")[:40].strip("-")


async def _slug_libre(db: AsyncSession, nombre: str) -> str:
    base = slug_de(nombre)
    slug, n = base, 2
    while await db.scalar(select(Tenant.id).where(Tenant.slug == slug)):
        slug, n = f"{base}-{n}", n + 1
    return slug


async def listar(db: AsyncSession) -> list[CopropiedadOut]:
    conteos = {r.tenant_id: r for r in await db.execute(text("SELECT * FROM plataforma_resumen()"))}
    tenants = await db.scalars(select(Tenant).where(Tenant.deleted_at.is_(None)).order_by(Tenant.is_demo, Tenant.name))
    return [_out(t, conteos.get(t.id)) for t in tenants]


def _out(t: Tenant, c: object | None) -> CopropiedadOut:
    def n(campo: str) -> int:
        return int(getattr(c, campo, 0) or 0)

    return CopropiedadOut(
        id=t.id,
        nombre=t.name,
        slug=t.slug,
        nit=t.nit,
        ciudad=t.city,
        direccion=t.address,
        is_demo=t.is_demo,
        creada_en=t.created_at,
        unidades=n("unidades"),
        usuarios=n("usuarios"),
        administradores=n("administradores"),
        invitaciones_pendientes=n("invitaciones_pendientes"),
    )


async def crear(db: AsyncSession, dueno: User, body: CopropiedadIn) -> tuple[CopropiedadOut, bool, Correo]:
    if body.nit and await db.scalar(select(Tenant.id).where(Tenant.nit == body.nit, Tenant.deleted_at.is_(None))):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe una copropiedad con el NIT {body.nit}")
    t = Tenant(
        name=body.nombre,
        slug=await _slug_libre(db, body.nombre),
        nit=body.nit,
        city=body.ciudad,
        address=body.direccion,
        is_demo=False,
    )
    db.add(t)
    await db.flush()
    await set_rls_context(db, tenant_id=t.id, user_id=dueno.id, role="SYSTEM")
    for semilla in SEMILLAS:
        await db.execute(text(f"SELECT {semilla}(:t)"), {"t": t.id})
    ctx = TenantContext(tenant_id=t.id, user_id=dueno.id, role=UserRole.ADMIN, is_demo=False)
    _, nuevo, correo = await usuarios.invitar(
        db,
        ctx,
        InvitacionIn(email=body.admin_email, nombre=body.admin_nombre, rol=UserRole.ADMIN),
        invita=dueno.full_name,
    )
    await db.refresh(t)
    return await _con_conteos(db, t), nuevo, correo


async def _con_conteos(db: AsyncSession, t: Tenant) -> CopropiedadOut:
    conteos = {r.tenant_id: r for r in await db.execute(text("SELECT * FROM plataforma_resumen()"))}
    return _out(t, conteos.get(t.id))


async def actualizar(db: AsyncSession, tenant_id: uuid.UUID, body: CopropiedadUpdate) -> CopropiedadOut:
    t = await db.get(Tenant, tenant_id)
    if t is None or t.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Copropiedad no encontrada")
    cambios = body.model_dump(exclude_unset=True)
    for campo, columna in (("nombre", "name"), ("nit", "nit"), ("ciudad", "city"), ("direccion", "address")):
        if campo in cambios:
            setattr(t, columna, cambios[campo])
    if "is_demo" in cambios and cambios["is_demo"] is not None:
        t.is_demo = cambios["is_demo"]
    await db.flush()
    await db.refresh(t)
    return await _con_conteos(db, t)


async def enlaces_pendientes(db: AsyncSession, dueno: User, tenant_id: uuid.UUID) -> list[EnlaceInvitacion]:
    """Enlaces NUEVOS para los administradores que aún no activan su cuenta (anulan los enviados antes).

    Solo administradores sin clave: a una cuenta activa nunca se le genera un enlace (sería tomar su cuenta).
    """
    t = await db.get(Tenant, tenant_id)
    if t is None or t.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Copropiedad no encontrada")
    await set_rls_context(db, tenant_id=t.id, user_id=dueno.id, role="SYSTEM")
    pendientes = await db.scalars(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.tenant_id == t.id,
            Membership.role == UserRole.ADMIN,
            User.password_hash.is_(None),
            User.is_active,
        )
        .order_by(User.full_name)
    )
    salida = []
    for user in pendientes:
        url = await enlaces.emitir(db, user, enlaces.INVITACION, tenant_id=t.id, creado_por=dueno.id)
        salida.append(EnlaceInvitacion(nombre=user.full_name, email=user.email, enlace=url))
    if not salida:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Esta copropiedad no tiene administradores con la invitación pendiente"
        )
    return salida


async def eliminar(db: AsyncSession, tenant_id: uuid.UUID, confirmacion: str) -> None:
    """Borrado lógico (deleted_at): desaparece del panel y del selector de sus usuarios y nadie puede entrar.
    Los datos se conservan en la base. Las invitaciones pendientes de esa copropiedad dejan de servir."""
    t = await db.get(Tenant, tenant_id)
    if t is None or t.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Copropiedad no encontrada")
    if confirmacion.strip() != t.name.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escriba el nombre exacto de la copropiedad para confirmar")
    ahora = datetime.now(UTC)
    t.deleted_at = ahora
    await db.execute(
        update(AccountToken).where(AccountToken.tenant_id == t.id, AccountToken.used_at.is_(None)).values(used_at=ahora)
    )
    await db.flush()
