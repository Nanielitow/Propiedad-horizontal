"""Catálogos del módulo: categorías de activos y contratistas."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CategoriaActivo, Contratista, Document
from app.schemas.activos import ContratistaIn, ContratistaUpdate
from app.services.activos.dominio import PUEDE_GESTIONAR_CONTRATISTAS, PUEDE_VER
from app.services.comun import Actor, NoEncontrado, ValidacionError, exigir


async def listar_categorias(db: AsyncSession, actor: Actor) -> list[CategoriaActivo]:
    exigir(actor, PUEDE_VER, "consultar las categorías")
    return list(
        await db.scalars(select(CategoriaActivo).where(CategoriaActivo.activo).order_by(CategoriaActivo.nombre))
    )


async def categoria(db: AsyncSession, actor: Actor, categoria_id: uuid.UUID) -> CategoriaActivo:
    c = await db.get(CategoriaActivo, categoria_id)
    if c is None or c.tenant_id != actor.tenant_id or not c.activo:
        raise NoEncontrado("Categoría no encontrada")
    return c


async def contratista(db: AsyncSession, actor: Actor, contratista_id: uuid.UUID | None) -> Contratista | None:
    """Valida que el contratista exista en la copropiedad (None pasa tal cual)."""
    if contratista_id is None:
        return None
    c = await db.get(Contratista, contratista_id)
    if c is None or c.tenant_id != actor.tenant_id:
        raise NoEncontrado("Contratista no encontrado")
    return c


async def _documento(db: AsyncSession, actor: Actor, document_id: uuid.UUID | None) -> None:
    if document_id is None:
        return
    doc = await db.scalar(
        select(Document.id).where(
            Document.id == document_id, Document.tenant_id == actor.tenant_id, Document.deleted_at.is_(None)
        )
    )
    if doc is None:
        raise NoEncontrado("Documento no encontrado")


async def listar_contratistas(db: AsyncSession, actor: Actor, *, incluir_inactivos: bool = False) -> list[Contratista]:
    exigir(actor, PUEDE_VER, "consultar los contratistas")
    q = select(Contratista).order_by(Contratista.razon_social)
    if not incluir_inactivos:
        q = q.where(Contratista.activo)
    return list(await db.scalars(q))


async def crear_contratista(db: AsyncSession, actor: Actor, data: ContratistaIn) -> Contratista:
    exigir(actor, PUEDE_GESTIONAR_CONTRATISTAS, "registrar contratistas")
    if data.nit and await db.scalar(select(Contratista.id).where(Contratista.nit == data.nit)):
        raise ValidacionError(f"Ya existe un contratista con el NIT {data.nit}")
    await _documento(db, actor, data.contrato_documento_id)
    c = Contratista(id=uuid.uuid4(), tenant_id=actor.tenant_id, **data.model_dump())
    db.add(c)
    await db.flush()
    return c


async def editar_contratista(
    db: AsyncSession, actor: Actor, contratista_id: uuid.UUID, data: ContratistaUpdate
) -> Contratista:
    exigir(actor, PUEDE_GESTIONAR_CONTRATISTAS, "editar contratistas")
    c = await contratista(db, actor, contratista_id)
    assert c is not None
    cambios = data.model_dump(exclude_unset=True)
    if cambios.get("nit") and cambios["nit"] != c.nit:
        if await db.scalar(select(Contratista.id).where(Contratista.nit == cambios["nit"], Contratista.id != c.id)):
            raise ValidacionError(f"Ya existe un contratista con el NIT {cambios['nit']}")
    await _documento(db, actor, cambios.get("contrato_documento_id"))
    for campo, valor in cambios.items():
        setattr(c, campo, valor)
    ini, fin = c.vigencia_contrato_inicio, c.vigencia_contrato_fin
    if ini and fin and fin < ini:
        raise ValidacionError("El fin del contrato es anterior a su inicio")
    await db.flush()
    return c
