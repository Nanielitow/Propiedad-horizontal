"""Consultas del portal: bandeja y detalle de PQRS, circulares, zonas, reservas e inicio del residente.

La RLS decide qué filas ve cada rol; aquí se arma la lectura (nombres, plazos, adjuntos con
URL firmada de descarga).
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CarteraConfig,
    Circular,
    CircularLectura,
    Document,
    Novedad,
    Persona,
    Pqrs,
    PqrsMensaje,
    Reserva,
    UnidadPersona,
    Unit,
    User,
    ZonaSocial,
)
from app.models.enums import CategoriaPqrs, EstadoCircular, EstadoPqrs, EstadoReserva, UserRole
from app.schemas.portal_out import (
    AdjuntoOut,
    CircularOut,
    InicioResidente,
    MensajeOut,
    PendientesPersonal,
    PqrsDetalle,
    PqrsResumen,
    PqrsResumenBandeja,
    ReservaOut,
    ZonaOut,
)
from app.services.cartera import comun as cartera
from app.services.comun import Actor, hoy_bogota
from app.services.portal import adjuntos as adj
from app.services.portal import circulares as svc_circulares
from app.services.portal import dominio as d
from app.services.portal.pqrs import _puede_gestionar, obtener
from app.services.unidades.consultas import orden_unidad

R = UserRole
E = EstadoPqrs


def _nombre(full: str | None) -> str:
    return (full or "").split(" (")[0]


async def _usuarios(db: AsyncSession, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    ids_ok = {i for i in ids if i}
    if not ids_ok:
        return {}
    return {
        i: _nombre(n) for i, n in (await db.execute(select(User.id, User.full_name).where(User.id.in_(ids_ok)))).all()
    }


async def _etiquetas(db: AsyncSession, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    ids_ok = {i for i in ids if i}
    if not ids_ok:
        return {}
    return {u.id: u.etiqueta for u in await db.scalars(select(Unit).where(Unit.id.in_(ids_ok)))}


def _adjuntos(lista: list[dict[str, object]]) -> list[AdjuntoOut]:
    return [
        AdjuntoOut(
            nombre=str(a.get("nombre")), tipo=str(a.get("tipo")), tamano=a.get("tamano"), url=adj.url_descarga(a)
        )  # type: ignore[arg-type]
        for a in lista
    ]


# --- PQRS ---------------------------------------------------------------------------------


def _resumen(
    p: Pqrs, usuarios: dict[uuid.UUID, str], etiquetas: dict[uuid.UUID, str], mensajes: int, hoy: date
) -> PqrsResumen:
    abierta = p.estado in d.ABIERTAS
    restantes = d.dias_habiles_entre(hoy, p.fecha_limite) if abierta else None
    return PqrsResumen(
        id=p.id,
        radicado=p.radicado,
        tipo=p.tipo,
        categoria=p.categoria,
        asunto=p.asunto,
        estado=p.estado,
        prioridad=p.prioridad,
        canal=p.canal,
        unidad=etiquetas.get(p.unidad_id) if p.unidad_id else None,
        solicitante_nombre=p.solicitante_nombre,
        asignado_a=usuarios.get(p.asignado_a_id) if p.asignado_a_id else None,
        fecha_limite=p.fecha_limite,
        dias_habiles_restantes=restantes,
        vencida=abierta and p.fecha_limite < hoy,
        calificacion=p.calificacion,
        mensajes=mensajes,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@dataclass(frozen=True)
class FiltroPqrs:
    estado: EstadoPqrs | None = None
    categoria: CategoriaPqrs | None = None
    solo_abiertas: bool = False
    vencidas: bool = False
    asignadas_a_mi: bool = False
    sin_asignar: bool = False
    texto: str | None = None


async def listar_pqrs(db: AsyncSession, actor: Actor, f: FiltroPqrs, *, limite: int = 200) -> list[PqrsResumen]:
    hoy = hoy_bogota()
    q = select(Pqrs).order_by(Pqrs.created_at.desc()).limit(limite)
    if actor.role == R.RESIDENTE:
        q = q.where(Pqrs.radicado_por_id == actor.user_id)  # además de la RLS: solo las propias
    if f.estado:
        q = q.where(Pqrs.estado == f.estado)
    if f.solo_abiertas or f.vencidas:
        q = q.where(Pqrs.estado.in_(d.ABIERTAS))
    if f.vencidas:
        q = q.where(Pqrs.fecha_limite < hoy)
    if f.categoria:
        q = q.where(Pqrs.categoria == f.categoria)
    if f.asignadas_a_mi:
        q = q.where(Pqrs.asignado_a_id == actor.user_id)
    if f.sin_asignar:
        q = q.where(Pqrs.asignado_a_id.is_(None))
    if f.texto and f.texto.strip():
        t = f.texto.strip()
        cond = [Pqrs.asunto.ilike(f"%{t}%"), Pqrs.solicitante_nombre.ilike(f"%{t}%")]
        digitos = "".join(c for c in t if c.isdigit())
        if digitos:
            cond.append(Pqrs.consecutivo == int(digitos[-6:]))
        q = q.where(or_(*cond))
    ps = list(await db.scalars(q))
    usuarios = await _usuarios(db, {p.asignado_a_id for p in ps})
    etiquetas = await _etiquetas(db, {p.unidad_id for p in ps})
    conteos = dict(
        (
            await db.execute(
                select(PqrsMensaje.pqrs_id, func.count())
                .where(PqrsMensaje.pqrs_id.in_([p.id for p in ps]))
                .group_by(PqrsMensaje.pqrs_id)
            )
        ).all()
    )
    return [_resumen(p, usuarios, etiquetas, conteos.get(p.id, 0), hoy) for p in ps]


async def detalle_pqrs(db: AsyncSession, actor: Actor, pqrs_id: uuid.UUID) -> PqrsDetalle:
    p = await obtener(db, actor, pqrs_id)
    mensajes = list(
        await db.scalars(select(PqrsMensaje).where(PqrsMensaje.pqrs_id == p.id).order_by(PqrsMensaje.created_at))
    )
    usuarios = await _usuarios(db, {p.asignado_a_id, *(m.autor_id for m in mensajes)})
    etiquetas = await _etiquetas(db, {p.unidad_id})
    codigo = await db.scalar(select(Novedad.codigo).where(Novedad.id == p.novedad_id)) if p.novedad_id else None
    base = _resumen(p, usuarios, etiquetas, len(mensajes), hoy_bogota())
    gestiona = _puede_gestionar(actor, p)
    return PqrsDetalle(
        **base.model_dump(),
        descripcion=p.descripcion,
        solicitante_contacto=p.solicitante_contacto if gestiona or p.radicado_por_id == actor.user_id else None,
        adjuntos=_adjuntos(p.adjuntos),
        comentario_calificacion=p.comentario_calificacion,
        respondida_at=p.respondida_at,
        cerrada_at=p.cerrada_at,
        novedad_id=p.novedad_id,
        novedad_codigo=codigo,
        hilo=[
            MensajeOut(
                id=m.id,
                # Al residente no se le revela quién del personal escribió: firma la administración
                autor=usuarios.get(m.autor_id, "")
                if (gestiona or m.autor_id == actor.user_id or m.autor_rol == "RESIDENTE")
                else "Administración",
                autor_rol=m.autor_rol,
                es_mio=m.autor_id == actor.user_id,
                texto=m.texto,
                interno=m.interno,
                es_respuesta=m.es_respuesta,
                adjuntos=_adjuntos(m.adjuntos),
                created_at=m.created_at,
            )
            for m in mensajes
        ],
        es_mia=p.radicado_por_id == actor.user_id,
        puede_gestionar=gestiona,
    )


async def resumen_bandeja(db: AsyncSession, actor: Actor) -> PqrsResumenBandeja:
    hoy = hoy_bogota()
    ps = list(await db.scalars(select(Pqrs)))
    por_estado: dict[str, int] = defaultdict(int)
    for p in ps:
        por_estado[p.estado.value] += 1
    abiertas = [p for p in ps if p.estado in d.ABIERTAS]
    respondidas = [p for p in ps if p.respondida_at]
    tiempo = (
        (
            Decimal(
                sum(
                    d.dias_habiles_entre(p.created_at.date(), p.respondida_at.date())
                    for p in respondidas
                    if p.respondida_at
                )
            )
            / len(respondidas)
        ).quantize(Decimal("0.1"))
        if respondidas
        else None
    )
    calif = [p.calificacion for p in ps if p.calificacion]
    return PqrsResumenBandeja(
        por_estado=dict(por_estado),
        abiertas=len(abiertas),
        vencidas=sum(1 for p in abiertas if p.fecha_limite < hoy),
        por_vencer=sum(1 for p in abiertas if 0 <= d.dias_habiles_entre(hoy, p.fecha_limite) <= 3),
        sin_asignar=sum(1 for p in abiertas if p.asignado_a_id is None),
        tiempo_respuesta_promedio_dias=tiempo,
        satisfaccion_promedio=(Decimal(sum(calif)) / len(calif)).quantize(Decimal("0.1")) if calif else None,
    )


# --- Circulares -----------------------------------------------------------------------------


async def _circulares_out(db: AsyncSession, actor: Actor, cs: list[Circular]) -> list[CircularOut]:
    leidas = set(
        await db.scalars(
            select(CircularLectura.circular_id).where(
                CircularLectura.user_id == actor.user_id, CircularLectura.circular_id.in_([c.id for c in cs])
            )
        )
    )
    docs = dict(
        (
            await db.execute(
                select(Document.id, Document.title).where(Document.id.in_({c.document_id for c in cs if c.document_id}))
            )
        ).all()
    )
    personal = actor.role in d.PUEDE_VER_LECTURAS
    conteos: dict[uuid.UUID, int] = {}
    if personal:
        conteos = dict(
            (
                await db.execute(
                    select(CircularLectura.circular_id, func.count())
                    .where(CircularLectura.circular_id.in_([c.id for c in cs]))
                    .group_by(CircularLectura.circular_id)
                )
            ).all()
        )
    out = []
    for c in cs:
        total = None
        if personal and c.estado != EstadoCircular.BORRADOR:
            total = len({x.user_id for x in await svc_circulares.destinatarios(db, c) if x.user_id})
        out.append(
            CircularOut(
                id=c.id,
                numero=f"{c.publicada_at.year}-{c.consecutivo:03d}" if c.consecutivo and c.publicada_at else None,
                titulo=c.titulo,
                cuerpo=c.cuerpo,
                categoria=c.categoria,
                importante=c.importante,
                torres=c.torres,
                estado=c.estado,
                document_id=c.document_id,
                documento_titulo=docs.get(c.document_id) if c.document_id else None,
                enviar_correo=c.enviar_correo,
                publicada_at=c.publicada_at,
                vigente_hasta=c.vigente_hasta,
                leida=c.id in leidas,
                lecturas=conteos.get(c.id, 0) if personal else None,
                destinatarios_con_cuenta=total,
                correos_enviados=c.correos_enviados,
                created_at=c.created_at,
            )
        )
    return out


async def listar_circulares(db: AsyncSession, actor: Actor, *, incluir_archivadas: bool = False) -> list[CircularOut]:
    q = select(Circular).order_by(Circular.publicada_at.desc().nulls_first(), Circular.created_at.desc())
    if not incluir_archivadas:
        q = q.where(Circular.estado != EstadoCircular.ARCHIVADA)
    cs = list(await db.scalars(q))
    torres = await svc_circulares.torres_del_usuario(db, actor)
    cs = [c for c in cs if svc_circulares.le_aplica(c, torres)]
    return await _circulares_out(db, actor, cs)


async def circular(db: AsyncSession, actor: Actor, circular_id: uuid.UUID) -> CircularOut:
    c = await svc_circulares.obtener(db, actor, circular_id)
    return (await _circulares_out(db, actor, [c]))[0]


# --- Zonas y reservas ------------------------------------------------------------------------


def zona_out(z: ZonaSocial) -> ZonaOut:
    return ZonaOut.model_validate(z, from_attributes=True)


async def zonas(db: AsyncSession, actor: Actor) -> list[ZonaOut]:
    q = select(ZonaSocial).order_by(ZonaSocial.nombre)
    if actor.role == R.RESIDENTE:
        q = q.where(ZonaSocial.activo.is_(True), ZonaSocial.reservable_residentes.is_(True))
    return [zona_out(z) for z in await db.scalars(q)]


async def reservas_out(db: AsyncSession, rs: list[Reserva]) -> list[ReservaOut]:
    zonas_ = {z.id: z for z in await db.scalars(select(ZonaSocial).where(ZonaSocial.id.in_({r.zona_id for r in rs})))}
    etiquetas = await _etiquetas(db, {r.unidad_id for r in rs})
    salida = []
    for r in rs:
        z = zonas_.get(r.zona_id)
        tarifa = None
        if z and (z.tarifa_alquiler or z.tarifa_aseo):
            tarifa = (z.tarifa_alquiler or Decimal(0)) + (z.tarifa_aseo or Decimal(0))
        salida.append(
            ReservaOut(
                id=r.id,
                zona_id=r.zona_id,
                zona=z.nombre if z else "",
                unidad_id=r.unidad_id,
                unidad=etiquetas.get(r.unidad_id) if r.unidad_id else None,
                solicitante=r.solicitante,
                fecha_evento=r.fecha_evento,
                hora_inicio=r.hora_inicio,
                hora_fin=r.hora_fin,
                numero_asistentes=r.numero_asistentes,
                estado=r.estado,
                observaciones=r.observaciones,
                solicitada_en_portal=r.solicitada_en_portal,
                motivo_decision=r.motivo_decision,
                decidida_at=r.decidida_at,
                tarifa_total=tarifa,
                created_at=r.created_at,
            )
        )
    return salida


# --- Inicio -------------------------------------------------------------------------------------


async def inicio_residente(db: AsyncSession, actor: Actor) -> InicioResidente:
    hoy = hoy_bogota()
    usuario = await db.get(User, actor.user_id)
    unidades = list(
        await db.scalars(
            select(Unit)
            .join(UnidadPersona, UnidadPersona.unidad_id == Unit.id)
            .join(Persona, Persona.id == UnidadPersona.persona_id)
            .where(
                Persona.user_id == actor.user_id, UnidadPersona.fecha_fin.is_(None), Unit.unidad_principal_id.is_(None)
            )
            .distinct()
        )
    )
    unidades.sort(key=orden_unidad)
    saldo = vencido = None
    if unidades and await db.get(CarteraConfig, actor.tenant_id) is not None:
        saldo = sum([await cartera.saldo_unidad(db, u.id) for u in unidades], Decimal(0))
        vencido = sum([await cartera.saldo_unidad(db, u.id, vencido_a=hoy) for u in unidades], Decimal(0))
    rs = list(
        await db.scalars(
            select(Reserva)
            .where(
                Reserva.fecha_evento >= hoy, Reserva.estado.in_([EstadoReserva.SOLICITADA, EstadoReserva.CONFIRMADA])
            )
            .order_by(Reserva.fecha_evento)
            .limit(3)
        )
    )
    mias = await listar_pqrs(db, actor, FiltroPqrs(), limite=50)
    circs = [c for c in await listar_circulares(db, actor) if c.estado == EstadoCircular.PUBLICADA and not c.leida]
    zonas_n = await db.scalar(
        select(func.count())
        .select_from(ZonaSocial)
        .where(ZonaSocial.activo.is_(True), ZonaSocial.reservable_residentes.is_(True))
    )
    return InicioResidente(
        nombre=_nombre(usuario.full_name if usuario else ""),
        unidades=[u.etiqueta for u in unidades],
        saldo_total=saldo,
        saldo_vencido=vencido,
        al_dia=(vencido == 0) if vencido is not None else None,
        proximas_reservas=await reservas_out(db, rs),
        pqrs_abiertas=[p for p in mias if p.estado in (E.RADICADA, E.EN_TRAMITE, E.RESPONDIDA)][:5],
        pqrs_por_calificar=sum(1 for p in mias if p.estado == E.RESPONDIDA),
        circulares_sin_leer=circs[:5],
        zonas_reservables=zonas_n or 0,
    )


async def pendientes_personal(db: AsyncSession, actor: Actor) -> PendientesPersonal:
    hoy = hoy_bogota()
    abiertas = list(await db.scalars(select(Pqrs).where(Pqrs.estado.in_(d.ABIERTAS))))
    por_decidir = await db.scalar(
        select(func.count())
        .select_from(Reserva)
        .where(Reserva.estado == EstadoReserva.SOLICITADA, Reserva.fecha_evento >= hoy)
    )
    borradores = await db.scalar(
        select(func.count()).select_from(Circular).where(Circular.estado == EstadoCircular.BORRADOR)
    )
    return PendientesPersonal(
        pqrs_abiertas=len(abiertas),
        pqrs_vencidas=sum(1 for p in abiertas if p.fecha_limite < hoy),
        pqrs_sin_asignar=sum(1 for p in abiertas if p.asignado_a_id is None),
        reservas_por_decidir=por_decidir or 0,
        circulares_borrador=borradores or 0,
    )
