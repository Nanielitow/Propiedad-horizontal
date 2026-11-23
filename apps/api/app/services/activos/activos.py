"""Hoja de vida de los activos: registro, edición, baja, QR, documentos y horómetro."""

import uuid
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Activo, ActivoDocumento, Deadline, Document, LecturaUso
from app.models.enums import DeadlineStatus, EstadoActivo, UserRole
from app.schemas.activos import ActivoIn, ActivoUpdate, BajaIn, LecturaIn, VinculoDocumentoIn
from app.services.activos import catalogo
from app.services.activos.dominio import (
    PUEDE_CREAR_ACTIVO,
    PUEDE_DAR_DE_BAJA,
    PUEDE_DOCUMENTAR,
    PUEDE_EDITAR_ACTIVO,
    PUEDE_REGISTRAR_MANTENIMIENTO,
    PUEDE_VER,
    nuevo_qr_token,
)
from app.services.comun import Actor, NoEncontrado, ValidacionError, exigir, fijar_motivo, hoy_bogota


async def obtener(db: AsyncSession, actor: Actor, activo_id: uuid.UUID) -> Activo:
    exigir(actor, PUEDE_VER, "consultar activos")
    a = await db.get(Activo, activo_id)
    if a is None or a.tenant_id != actor.tenant_id:
        raise NoEncontrado("Activo no encontrado")
    return a


async def por_qr(db: AsyncSession, actor: Actor, token: str) -> Activo:
    exigir(actor, PUEDE_VER, "consultar activos")
    a = await db.scalar(select(Activo).where(Activo.qr_token == token))
    if a is None or a.tenant_id != actor.tenant_id:
        # Mismo mensaje si es de otra copropiedad: no se revela que el código existe
        raise NoEncontrado("Código QR no reconocido o de otra copropiedad")
    return a


def _vigente(a: Activo) -> None:
    if a.estado == EstadoActivo.DADO_DE_BAJA:
        raise ValidacionError(f"El activo {a.codigo_interno} está dado de baja")


async def _validar_referencias(db: AsyncSession, actor: Actor, datos: dict[str, object]) -> None:
    if datos.get("categoria_id"):  # los subtipos de la categoría son sugerencias: se admite uno nuevo
        await catalogo.categoria(db, actor, datos["categoria_id"])  # type: ignore[arg-type]
    for campo in ("instalador_id", "mantenedor_id"):
        if datos.get(campo):
            await catalogo.contratista(db, actor, datos[campo])  # type: ignore[arg-type]
    hoy = hoy_bogota()
    instalacion = datos.get("fecha_instalacion")
    if isinstance(instalacion, date) and instalacion > hoy:
        raise ValidacionError("La fecha de instalación no puede estar en el futuro")


async def crear_activo(db: AsyncSession, actor: Actor, data: ActivoIn) -> Activo:
    exigir(actor, PUEDE_CREAR_ACTIVO, "registrar activos")
    datos = data.model_dump()
    await _validar_referencias(db, actor, datos)
    await fijar_motivo(db, None)
    a = Activo(id=uuid.uuid4(), tenant_id=actor.tenant_id, qr_token=nuevo_qr_token(), **datos)
    db.add(a)
    await db.flush()
    return a


async def editar_activo(db: AsyncSession, actor: Actor, activo_id: uuid.UUID, data: ActivoUpdate) -> Activo:
    exigir(actor, PUEDE_EDITAR_ACTIVO, "editar activos")
    a = await obtener(db, actor, activo_id)
    _vigente(a)
    cambios = data.model_dump(exclude_unset=True, exclude={"motivo"})
    if not cambios:
        raise ValidacionError("No hay cambios para guardar")
    if "nombre" in cambios and not cambios["nombre"]:
        raise ValidacionError("El nombre es obligatorio")
    await _validar_referencias(db, actor, cambios)
    await fijar_motivo(db, data.motivo)
    for campo, valor in cambios.items():
        setattr(a, campo, valor)
    await db.flush()
    await fijar_motivo(db, None)
    return a


async def dar_de_baja(db: AsyncSession, actor: Actor, activo_id: uuid.UUID, data: BajaIn) -> Activo:
    """Reemplaza al borrado: el activo y todo su historial se conservan."""
    exigir(actor, PUEDE_DAR_DE_BAJA, "dar de baja activos")
    a = await obtener(db, actor, activo_id)
    _vigente(a)
    fecha = data.fecha_baja or hoy_bogota()
    if fecha > hoy_bogota():
        raise ValidacionError("La fecha de baja no puede estar en el futuro")
    await fijar_motivo(db, data.motivo)
    a.estado = EstadoActivo.DADO_DE_BAJA
    a.motivo_baja = data.motivo
    a.fecha_baja = fecha
    await db.flush()
    await fijar_motivo(db, None)
    return a


async def regenerar_qr(db: AsyncSession, actor: Actor, activo_id: uuid.UUID) -> Activo:
    """Si una etiqueta se pierde o se daña: el QR anterior deja de funcionar."""
    exigir(actor, PUEDE_EDITAR_ACTIVO, "regenerar el código QR")
    a = await obtener(db, actor, activo_id)
    _vigente(a)
    await fijar_motivo(db, "Código QR regenerado")
    a.qr_token = nuevo_qr_token()
    await db.flush()
    await fijar_motivo(db, None)
    return a


async def vincular_documento(
    db: AsyncSession, actor: Actor, activo_id: uuid.UUID, data: VinculoDocumentoIn
) -> ActivoDocumento:
    exigir(actor, PUEDE_DOCUMENTAR, "vincular documentos")
    a = await obtener(db, actor, activo_id)
    _vigente(a)
    doc = await db.scalar(
        select(Document.id).where(
            Document.id == data.document_id, Document.tenant_id == actor.tenant_id, Document.deleted_at.is_(None)
        )
    )
    if doc is None:
        raise NoEncontrado("Documento no encontrado")
    existente = await db.get(ActivoDocumento, (activo_id, data.document_id))
    if existente is not None:
        raise ValidacionError("Ese documento ya está vinculado al activo")
    v = ActivoDocumento(
        activo_id=activo_id,
        document_id=data.document_id,
        tenant_id=actor.tenant_id,
        tipo=data.tipo,
        fecha_documento=data.fecha_documento,
        vinculado_por_id=actor.user_id,
    )
    db.add(v)
    await db.flush()
    return v


async def desvincular_documento(db: AsyncSession, actor: Actor, activo_id: uuid.UUID, document_id: uuid.UUID) -> None:
    """Quita el vínculo; el documento sigue en el archivo de la copropiedad."""
    exigir(actor, PUEDE_DOCUMENTAR, "desvincular documentos")
    await obtener(db, actor, activo_id)
    resultado = await db.execute(
        delete(ActivoDocumento).where(
            ActivoDocumento.activo_id == activo_id, ActivoDocumento.document_id == document_id
        )
    )
    if not resultado.rowcount:  # type: ignore[attr-defined]
        raise NoEncontrado("Ese documento no está vinculado al activo")


async def registrar_lectura(db: AsyncSession, actor: Actor, activo_id: uuid.UUID, data: LecturaIn) -> LecturaUso:
    """Horómetro para planes por horas de uso (también desde el QR, por el técnico)."""
    exigir(actor, PUEDE_REGISTRAR_MANTENIMIENTO, "registrar lecturas de uso")
    a = await obtener(db, actor, activo_id)
    _vigente(a)
    anterior = await db.scalar(
        select(LecturaUso.horas_acumuladas)
        .where(LecturaUso.activo_id == activo_id)
        .order_by(LecturaUso.horas_acumuladas.desc())
        .limit(1)
    )
    if anterior is not None and data.horas_acumuladas < anterior:
        raise ValidacionError(f"La lectura ({data.horas_acumuladas} h) es menor que la anterior ({anterior} h)")
    lectura = LecturaUso(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        activo_id=activo_id,
        horas_acumuladas=data.horas_acumuladas,
        registrado_por_id=actor.user_id,
    )
    db.add(lectura)
    await db.flush()
    return lectura


def puede_ver_costos(role: UserRole) -> bool:
    return role in (UserRole.ADMIN, UserRole.CONTABILIDAD)


async def vencimientos(db: AsyncSession, actor: Actor, activo_id: uuid.UUID) -> list[Deadline]:
    """Vencimientos detectados por la IA en los documentos vinculados al activo (contratos,
    garantías, certificados). El módulo de vencimientos es de la administración: para otros
    roles RLS devuelve una lista vacía."""
    await obtener(db, actor, activo_id)
    return list(
        await db.scalars(
            select(Deadline)
            .join(ActivoDocumento, ActivoDocumento.document_id == Deadline.document_id)
            .where(
                ActivoDocumento.activo_id == activo_id,
                Deadline.status.in_([DeadlineStatus.PENDING_REVIEW, DeadlineStatus.ACTIVE]),
            )
            .order_by(Deadline.due_date)
        )
    )
