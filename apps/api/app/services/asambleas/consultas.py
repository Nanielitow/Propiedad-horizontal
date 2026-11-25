"""Consultas de asambleas: listado y detalle en vivo (quórum, puntos con resultados, padrón)."""

import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asamblea, AsistenciaAsamblea, PadronAsamblea, PuntoAsamblea, VotoAsamblea
from app.models.enums import EstadoAsamblea, EstadoPunto, ModalidadAsamblea, TipoPunto, UserRole
from app.schemas.asambleas_out import AsambleaDetalle, AsambleaResumen, PadronOut, PuntoOut, QuorumOut, ResultadoOut
from app.services.asambleas import servicio as s
from app.services.comun import Actor
from app.services.unidades.consultas import orden_unidad

R = UserRole
PERSONAL = frozenset({R.ADMIN, R.AUXILIAR, R.CONSEJO, R.CONTABILIDAD})


def _quorum_out(q: s.d.Quorum) -> QuorumOut:
    return QuorumOut(
        presente=q.presente,
        total=q.total,
        porcentaje=q.porcentaje,
        unidades_presentes=q.unidades_presentes,
        unidades_total=q.unidades_total,
        hay_quorum=q.hay_quorum,
        falta=q.falta,
        mensaje=q.mensaje,
    )


async def listar(db: AsyncSession, actor: Actor) -> list[AsambleaResumen]:
    asambleas = list(await db.scalars(select(Asamblea).order_by(Asamblea.fecha_hora.desc())))
    puntos = dict(
        (await db.execute(select(PuntoAsamblea.asamblea_id, func.count()).group_by(PuntoAsamblea.asamblea_id))).all()
    )
    salida = []
    for a in asambleas:
        pct = None
        if a.estado in (EstadoAsamblea.EN_CURSO, EstadoAsamblea.CERRADA):
            pct = (
                (await s.quorum(db, a)).porcentaje
                if a.estado == EstadoAsamblea.EN_CURSO
                else await _quorum_maximo(db, a)
            )
        salida.append(_resumen(a, puntos.get(a.id, 0), pct))
    return salida


async def _quorum_maximo(db: AsyncSession, a: Asamblea) -> Decimal | None:
    """De una asamblea cerrada: el mayor quórum con que se votó (o el de asistencia total)."""
    maximo = await db.scalar(
        select(func.max(PuntoAsamblea.coeficiente_presente)).where(PuntoAsamblea.asamblea_id == a.id)
    )
    if maximo is None or not a.coeficiente_total:
        return None
    return (Decimal(maximo) / a.coeficiente_total * 100).quantize(Decimal("0.01"))


def _resumen(a: Asamblea, puntos: int, pct: Decimal | None) -> AsambleaResumen:
    return AsambleaResumen(
        id=a.id,
        consecutivo=a.consecutivo,
        titulo=a.titulo,
        tipo=a.tipo,
        modalidad=a.modalidad,
        convocatoria=a.convocatoria,
        fecha_hora=a.fecha_hora,
        lugar=a.lugar,
        estado=a.estado,
        convocada=a.circular_id is not None,
        puntos=puntos,
        quorum_pct=pct,
        acta_document_id=a.acta_document_id,
    )


async def detalle(db: AsyncSession, actor: Actor, asamblea_id: uuid.UUID) -> AsambleaDetalle:
    a = await s.obtener(db, actor, asamblea_id)
    puntos = list(
        await db.scalars(select(PuntoAsamblea).where(PuntoAsamblea.asamblea_id == a.id).order_by(PuntoAsamblea.orden))
    )
    padron = list(await db.scalars(select(PadronAsamblea).where(PadronAsamblea.asamblea_id == a.id)))
    asistencias = {
        x.unidad_id: x
        for x in await db.scalars(
            select(AsistenciaAsamblea).where(
                AsistenciaAsamblea.asamblea_id == a.id, AsistenciaAsamblea.retiro_at.is_(None)
            )
        )
    }
    etiqueta = {p.unidad_id: p.etiqueta for p in padron}
    mias = {p.unidad_id for p in padron if actor.user_id in (p.votante_user_ids or [])}
    conteos = dict(
        (
            await db.execute(
                select(VotoAsamblea.punto_id, func.count())
                .where(VotoAsamblea.asamblea_id == a.id)
                .group_by(VotoAsamblea.punto_id)
            )
        ).all()
    )
    mis_votos: dict[uuid.UUID, dict[str, str]] = defaultdict(dict)
    if mias:
        for pid, uid, opcion in (
            await db.execute(
                select(VotoAsamblea.punto_id, VotoAsamblea.unidad_id, VotoAsamblea.opcion).where(
                    VotoAsamblea.asamblea_id == a.id, VotoAsamblea.unidad_id.in_(mias)
                )
            )
        ).all():
            mis_votos[pid][etiqueta.get(uid, "")] = opcion

    q = await s.quorum(db, a) if a.estado != EstadoAsamblea.PROGRAMADA and a.coeficiente_total else None
    puntos_out = []
    for p in puntos:
        res = None
        if p.tipo == TipoPunto.VOTACION and p.estado != EstadoPunto.PENDIENTE:
            r = await s.calcular_resultado(db, a, p) if p.estado == EstadoPunto.EN_VOTACION or not p.resultado else None
            datos = dict(r.a_json() if r else p.resultado or {})
            # El JSONB no conserva el orden de las claves: se devuelven en el orden de las opciones del punto
            for clave in ("por_opcion", "unidades_por_opcion"):
                valores = datos.get(clave) or {}
                datos[clave] = {o: valores.get(o, 0) for o in p.opciones}  # type: ignore[union-attr]
            res = ResultadoOut(**datos)  # type: ignore[arg-type]
        puntos_out.append(
            PuntoOut(
                id=p.id,
                orden=p.orden,
                titulo=p.titulo,
                descripcion=p.descripcion,
                tipo=p.tipo,
                mayoria=p.mayoria,
                opciones=p.opciones,
                estado=p.estado,
                abierto_at=p.abierto_at,
                cerrado_at=p.cerrado_at,
                resultado=res,
                aprobado=p.aprobado,
                conclusion=p.conclusion,
                votos=conteos.get(p.id, 0),
                mis_votos=mis_votos.get(p.id, {}),
            )
        )

    personal = actor.role in PERSONAL
    visibles = padron if personal else [p for p in padron if p.unidad_id in mias]
    padron_out = []
    for p in sorted(visibles, key=lambda x: orden_unidad(_UnidadFicticia(x.etiqueta))):
        x = asistencias.get(p.unidad_id)
        padron_out.append(
            PadronOut(
                unidad_id=p.unidad_id,
                etiqueta=p.etiqueta,
                coeficiente=p.coeficiente,
                propietarios=p.propietarios,
                al_dia=p.al_dia if personal else None,
                presente=x is not None,
                asistencia_id=x.id if x else None,
                asistente=x.asistente_nombre if x else None,
                tipo=x.tipo if x else None,
                virtual=bool(x and x.virtual),
                llegada_at=x.llegada_at if x else None,
                con_cuenta=bool(p.votante_user_ids),
            )
        )
    return AsambleaDetalle(
        **_resumen(a, len(puntos), q.porcentaje if q else None).model_dump(),
        max_poderes_por_apoderado=a.max_poderes_por_apoderado,
        presidente=a.presidente,
        secretario=a.secretario,
        observaciones=a.observaciones,
        abierta_at=a.abierta_at,
        cerrada_at=a.cerrada_at,
        circular_id=a.circular_id,
        quorum=_quorum_out(q) if q else None,
        puntos_lista=puntos_out,
        padron=padron_out,
        soy_votante=bool(mias),
        puede_asistir_portal=bool(mias)
        and a.estado == EstadoAsamblea.EN_CURSO
        and a.modalidad != ModalidadAsamblea.PRESENCIAL,
    )


class _UnidadFicticia:
    """Para ordenar el padrón con el mismo criterio natural que el censo ('1-101' antes que '1-1001')."""

    def __init__(self, etiqueta: str) -> None:
        partes = etiqueta.split("-", 1)  # «1-101», «1-PQ-01»; sin torre: «L-01» se ordena por la letra
        self.tower, self.number = (partes[0], partes[1]) if len(partes) == 2 else ("", etiqueta)
