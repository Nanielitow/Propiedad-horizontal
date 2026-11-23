"""Consultas de lectura del módulo: buscador, detalles, listados y dashboard.

RLS filtra por copropiedad y por rol en cada consulta (el auxiliar solo ve lo
suyo); aquí solo se construyen las vistas que necesita la interfaz.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, case, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import (
    AuditoriaRecaudo,
    CierreCaja,
    ConceptoRecaudo,
    Consignacion,
    ConsignacionRecaudo,
    EntregaInterna,
    Recaudo,
    RecaudoItem,
    RecaudoParqueadero,
    Reserva,
    Unit,
    User,
    ZonaSocial,
)
from app.models.enums import EstadoConsignacion, EstadoEntrega, EstadoRecaudo, MedioPago
from app.schemas.recaudos_out import (
    AplicacionDetalle,
    AplicacionOut,
    AuditoriaOut,
    CierreDetalle,
    CierreOut,
    ConsignacionDetalle,
    ConsignacionOut,
    DashboardOut,
    EntregaDetalle,
    EntregaOut,
    ItemOut,
    ParqueaderoOut,
    RecaudoDetalle,
    RecaudoFila,
    RecaudosPagina,
    ReservaOut,
)
from app.services.recaudos.dominio import (
    PUEDE_VER_AUDITORIA,
    TZ,
    Actor,
    NoEncontrado,
    R,
    ValidacionError,
    exigir,
)
from app.services.storage.s3 import get_storage

PUEDE_VER_MOVIMIENTOS = frozenset({R.ADMIN, R.CONTABILIDAD, R.AUXILIAR})
PUEDE_VER_DASHBOARD = frozenset({R.ADMIN, R.CONTABILIDAD, R.CONSEJO})
_MIME = {"pdf": "application/pdf", "jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}

Receptor = aliased(User)


def _url_soporte(key: str | None, nombre: str) -> str | None:
    if not key:
        return None
    extension = key.rsplit(".", 1)[-1]
    return get_storage().presign_get(key, f"{nombre}.{extension}", _MIME.get(extension, "application/octet-stream"))


def _etiqueta_unidad(torre: str | None, numero: str | None) -> str | None:
    if numero is None:
        return None
    return f"Torre {torre} · {numero}" if torre else numero


# --- Filas de recaudo -------------------------------------------------------------


def _filas() -> Select[Any]:
    return (
        select(
            Recaudo,
            ConceptoRecaudo.nombre,
            Receptor.full_name,
            Unit.tower,
            Unit.number,
            RecaudoParqueadero.placa_vehiculo,
        )
        .join(ConceptoRecaudo, ConceptoRecaudo.id == Recaudo.concepto_id)
        .join(Receptor, Receptor.id == Recaudo.usuario_receptor_id)
        .outerjoin(Unit, Unit.id == Recaudo.unidad_id)
        .outerjoin(RecaudoParqueadero, RecaudoParqueadero.recaudo_id == Recaudo.id)
    )


def _fila(row: Any) -> RecaudoFila:
    r, concepto, receptor, torre, numero, placa = row
    return RecaudoFila(
        id=r.id,
        consecutivo=r.consecutivo,
        fecha_recaudo=r.fecha_recaudo,
        concepto_id=r.concepto_id,
        concepto=concepto,
        valor_recibido=r.valor_recibido,
        nombre_pagador=r.nombre_pagador,
        identificacion_pagador=r.identificacion_pagador,
        unidad_id=r.unidad_id,
        unidad=_etiqueta_unidad(torre, numero),
        medio_pago=r.medio_pago,
        estado=r.estado,
        numero_comprobante=r.numero_comprobante,
        usuario_receptor_id=r.usuario_receptor_id,
        receptor=receptor,
        placa=placa,
        tiene_soporte=r.soporte_key is not None,
        cierre_id=r.cierre_id,
        entrega_id=r.entrega_id,
    )


async def filas_por_ids(db: AsyncSession, ids: list[uuid.UUID]) -> list[RecaudoFila]:
    if not ids:
        return []
    rows = await db.execute(_filas().where(Recaudo.id.in_(ids)).order_by(Recaudo.consecutivo))
    return [_fila(r) for r in rows]


def _inicio_dia(d: date) -> datetime:
    return datetime.combine(d, time.min, TZ)


@dataclass
class FiltroRecaudos:
    desde: date | None = None
    hasta: date | None = None
    mes: int | None = None
    anio: int | None = None
    concepto_id: uuid.UUID | None = None
    medio_pago: MedioPago | None = None
    estados: list[EstadoRecaudo] = field(default_factory=list)
    usuario_id: uuid.UUID | None = None
    unidad_id: uuid.UUID | None = None
    pagador: str | None = None  # nombre o identificación
    placa: str | None = None
    consecutivo: int | None = None


def _aplicar_filtro(q: Select[Any], f: FiltroRecaudos) -> Select[Any]:
    if f.mes and not f.anio:
        raise ValidacionError("Para filtrar por mes indique también el año")
    if f.anio:
        if f.mes:
            inicio = date(f.anio, f.mes, 1)
            fin = date(f.anio + (f.mes == 12), f.mes % 12 + 1, 1)
        else:
            inicio, fin = date(f.anio, 1, 1), date(f.anio + 1, 1, 1)
        q = q.where(Recaudo.fecha_recaudo >= _inicio_dia(inicio), Recaudo.fecha_recaudo < _inicio_dia(fin))
    if f.desde:
        q = q.where(Recaudo.fecha_recaudo >= _inicio_dia(f.desde))
    if f.hasta:
        q = q.where(Recaudo.fecha_recaudo < _inicio_dia(f.hasta + timedelta(days=1)))
    if f.concepto_id:
        # También encuentra recaudos donde el concepto va en el desglose (p. ej. el aseo de un alquiler)
        q = q.where(
            or_(
                Recaudo.concepto_id == f.concepto_id,
                Recaudo.id.in_(select(RecaudoItem.recaudo_id).where(RecaudoItem.concepto_id == f.concepto_id)),
            )
        )
    if f.medio_pago:
        q = q.where(Recaudo.medio_pago == f.medio_pago)
    if f.estados:
        q = q.where(Recaudo.estado.in_(f.estados))
    if f.usuario_id:
        q = q.where(Recaudo.usuario_receptor_id == f.usuario_id)
    if f.unidad_id:
        q = q.where(Recaudo.unidad_id == f.unidad_id)
    if f.pagador:
        patron = f"%{f.pagador.strip()}%"
        q = q.where(or_(Recaudo.nombre_pagador.ilike(patron), Recaudo.identificacion_pagador.ilike(patron)))
    if f.placa:
        placa = "".join(ch for ch in f.placa.upper() if ch.isalnum())
        q = q.where(RecaudoParqueadero.placa_vehiculo.like(f"%{placa}%"))
    if f.consecutivo:
        q = q.where(Recaudo.consecutivo == f.consecutivo)
    return q


async def buscar_recaudos(
    db: AsyncSession, actor: Actor, filtro: FiltroRecaudos, *, page: int = 1, page_size: int = 25
) -> RecaudosPagina:
    exigir(actor, PUEDE_VER_MOVIMIENTOS, "consultar recaudos")
    page, page_size = max(1, page), min(max(1, page_size), 100)
    q = _aplicar_filtro(_filas(), filtro)
    base = q.subquery()
    total, suma = (
        await db.execute(
            select(
                func.count(),
                func.coalesce(
                    func.sum(case((base.c.estado != EstadoRecaudo.ANULADO, base.c.valor_recibido), else_=0)), 0
                ),
            ).select_from(base)
        )
    ).one()
    rows = await db.execute(
        q.order_by(Recaudo.fecha_recaudo.desc(), Recaudo.consecutivo.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    return RecaudosPagina(items=[_fila(r) for r in rows], total=total, suma=suma, page=page, page_size=page_size)


async def _saldos_por_consignar(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    rows = await db.execute(
        select(ConsignacionRecaudo.recaudo_id, func.sum(ConsignacionRecaudo.valor_aplicado))
        .join(Consignacion, Consignacion.id == ConsignacionRecaudo.consignacion_id)
        .where(ConsignacionRecaudo.recaudo_id.in_(ids), Consignacion.estado != EstadoConsignacion.RECHAZADA)
        .group_by(ConsignacionRecaudo.recaudo_id)
    )
    return dict(rows.all())


async def detalle_recaudo(db: AsyncSession, actor: Actor, recaudo_id: uuid.UUID) -> RecaudoDetalle:
    exigir(actor, PUEDE_VER_MOVIMIENTOS, "consultar recaudos")
    row = (await db.execute(_filas().where(Recaudo.id == recaudo_id))).first()
    if row is None:
        raise NoEncontrado("Recaudo no encontrado")
    r: Recaudo = row[0]
    fila = _fila(row)

    items = [
        ItemOut(concepto_id=i.concepto_id, concepto=nombre, descripcion=i.descripcion, valor=i.valor)
        for i, nombre in await db.execute(
            select(RecaudoItem, ConceptoRecaudo.nombre)
            .join(ConceptoRecaudo, ConceptoRecaudo.id == RecaudoItem.concepto_id)
            .where(RecaudoItem.recaudo_id == r.id)
            .order_by(RecaudoItem.valor.desc())
        )
    ]
    parqueadero = await db.get(RecaudoParqueadero, r.id)
    reserva = await db.get(Reserva, r.reserva_id) if r.reserva_id else None
    zona = await db.scalar(select(ZonaSocial.nombre).where(ZonaSocial.id == reserva.zona_id)) if reserva else None
    aplicaciones = [
        AplicacionOut(
            consignacion_id=c.id,
            consecutivo=c.consecutivo,
            banco_destino=c.banco_destino,
            referencia_bancaria=c.referencia_bancaria,
            estado=c.estado,
            valor_aplicado=valor,
        )
        for c, valor in await db.execute(
            select(Consignacion, ConsignacionRecaudo.valor_aplicado)
            .join(ConsignacionRecaudo, ConsignacionRecaudo.consignacion_id == Consignacion.id)
            .where(ConsignacionRecaudo.recaudo_id == r.id)
            .order_by(Consignacion.consecutivo)
        )
    ]
    aplicado = (await _saldos_por_consignar(db, [r.id])).get(r.id, Decimal(0))
    nombres = {
        uid: n
        for uid, n in await db.execute(
            select(User.id, User.full_name).where(
                User.id.in_([u for u in (r.anulado_por_id, r.verificado_por_id) if u])
            )
        )
    }
    pendiente = r.medio_pago == MedioPago.EFECTIVO and r.estado in (
        EstadoRecaudo.RECAUDADO_EN_CAJA,
        EstadoRecaudo.ENTREGADO_ADMINISTRACION,
    )
    return RecaudoDetalle(
        **fila.model_dump(),
        observaciones=r.observaciones,
        items=items,
        parqueadero=ParqueaderoOut.model_validate(parqueadero) if parqueadero else None,
        reserva=ReservaOut.model_validate(reserva) if reserva else None,
        zona=zona,
        consignaciones=aplicaciones,
        saldo_por_consignar=(r.valor_recibido - aplicado) if pendiente else Decimal(0),
        soporte_url=_url_soporte(r.soporte_key, f"soporte-recaudo-{r.consecutivo}"),
        anulado_por=nombres.get(r.anulado_por_id) if r.anulado_por_id else None,
        anulado_at=r.anulado_at,
        motivo_anulacion=r.motivo_anulacion,
        verificado_por=nombres.get(r.verificado_por_id) if r.verificado_por_id else None,
        verificado_at=r.verificado_at,
    )


async def auditoria_recaudo(db: AsyncSession, actor: Actor, recaudo_id: uuid.UUID) -> list[AuditoriaOut]:
    exigir(actor, PUEDE_VER_AUDITORIA, "consultar la auditoría")
    if await db.scalar(select(Recaudo.id).where(Recaudo.id == recaudo_id)) is None:
        raise NoEncontrado("Recaudo no encontrado")
    rows = await db.execute(
        select(AuditoriaRecaudo, User.full_name)
        .outerjoin(User, User.id == AuditoriaRecaudo.usuario_id)
        .where(AuditoriaRecaudo.recaudo_id == recaudo_id)
        .order_by(AuditoriaRecaudo.fecha_hora, AuditoriaRecaudo.id)
    )
    return [
        AuditoriaOut(
            id=a.id,
            entidad=a.entidad,
            accion=a.accion,
            usuario=nombre,
            fecha_hora=a.fecha_hora,
            valores_anteriores=a.valores_anteriores,
            valores_nuevos=a.valores_nuevos,
            motivo=a.motivo,
        )
        for a, nombre in rows
    ]


# --- Caja, entregas y consignaciones -----------------------------------------------


async def _nombres(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    return dict((await db.execute(select(User.id, User.full_name).where(User.id.in_(ids)))).all())


async def _conteo(db: AsyncSession, columna: Any, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ids:
        return {}
    rows = await db.execute(select(columna, func.count()).where(columna.in_(ids)).group_by(columna))
    return dict(rows.all())


def _cierre_out(c: CierreCaja, nombres: dict[uuid.UUID, str], conteo: dict[uuid.UUID, int]) -> CierreOut:
    return CierreOut(
        id=c.id,
        consecutivo=c.consecutivo,
        usuario_id=c.usuario_id,
        usuario=nombres.get(c.usuario_id, ""),
        inicio_turno=c.inicio_turno,
        fin_turno=c.fin_turno,
        saldo_inicial=c.saldo_inicial,
        saldo_esperado_sistema=c.saldo_esperado_sistema,
        valor_fisico_contado=c.valor_fisico_contado,
        diferencia=c.diferencia,
        tipo_diferencia=c.tipo_diferencia,
        observacion_justificacion=c.observacion_justificacion,
        cantidad_recaudos=conteo.get(c.id, 0),
    )


async def listar_cierres(
    db: AsyncSession, actor: Actor, *, usuario_id: uuid.UUID | None = None, limite: int = 50
) -> list[CierreOut]:
    exigir(actor, PUEDE_VER_MOVIMIENTOS, "consultar los cierres de caja")
    q = select(CierreCaja).order_by(CierreCaja.fin_turno.desc()).limit(min(limite, 200))
    if usuario_id:
        q = q.where(CierreCaja.usuario_id == usuario_id)
    cierres = list(await db.scalars(q))
    nombres = await _nombres(db, {c.usuario_id for c in cierres})
    conteo = await _conteo(db, Recaudo.cierre_id, [c.id for c in cierres])
    return [_cierre_out(c, nombres, conteo) for c in cierres]


async def detalle_cierre(db: AsyncSession, actor: Actor, cierre_id: uuid.UUID) -> CierreDetalle:
    exigir(actor, PUEDE_VER_MOVIMIENTOS, "consultar los cierres de caja")
    c = await db.get(CierreCaja, cierre_id)
    if c is None or c.tenant_id != actor.tenant_id:
        raise NoEncontrado("Cierre no encontrado")
    ids = list(await db.scalars(select(Recaudo.id).where(Recaudo.cierre_id == c.id)))
    out = _cierre_out(c, await _nombres(db, {c.usuario_id}), {c.id: len(ids)})
    return CierreDetalle(**out.model_dump(), recaudos=await filas_por_ids(db, ids))


def _entrega_out(e: EntregaInterna, nombres: dict[uuid.UUID, str], conteo: dict[uuid.UUID, int]) -> EntregaOut:
    return EntregaOut(
        id=e.id,
        consecutivo=e.consecutivo,
        entregado_por_id=e.entregado_por_id,
        entregado_por=nombres.get(e.entregado_por_id, ""),
        recibido_por_id=e.recibido_por_id,
        recibido_por=nombres.get(e.recibido_por_id, ""),
        fecha_entrega=e.fecha_entrega,
        valor_total=e.valor_total,
        valor_contado=e.valor_contado,
        estado=e.estado,
        confirmada_at=e.confirmada_at,
        observaciones=e.observaciones,
        cantidad_recaudos=conteo.get(e.id, 0),
    )


async def listar_entregas(
    db: AsyncSession,
    actor: Actor,
    *,
    estado: EstadoEntrega | None = None,
    para_mi: bool = False,
    limite: int = 50,
) -> list[EntregaOut]:
    exigir(actor, PUEDE_VER_MOVIMIENTOS, "consultar las entregas")
    q = select(EntregaInterna).order_by(EntregaInterna.fecha_entrega.desc()).limit(min(limite, 200))
    if estado:
        q = q.where(EntregaInterna.estado == estado)
    if para_mi:
        q = q.where(EntregaInterna.recibido_por_id == actor.user_id)
    entregas = list(await db.scalars(q))
    nombres = await _nombres(db, {u for e in entregas for u in (e.entregado_por_id, e.recibido_por_id)})
    conteo = await _conteo(db, Recaudo.entrega_id, [e.id for e in entregas])
    return [_entrega_out(e, nombres, conteo) for e in entregas]


async def detalle_entrega(db: AsyncSession, actor: Actor, entrega_id: uuid.UUID) -> EntregaDetalle:
    exigir(actor, PUEDE_VER_MOVIMIENTOS, "consultar las entregas")
    e = await db.get(EntregaInterna, entrega_id)
    if e is None or e.tenant_id != actor.tenant_id:
        raise NoEncontrado("Entrega no encontrada")
    ids = list(await db.scalars(select(Recaudo.id).where(Recaudo.entrega_id == e.id)))
    out = _entrega_out(e, await _nombres(db, {e.entregado_por_id, e.recibido_por_id}), {e.id: len(ids)})
    return EntregaDetalle(**out.model_dump(), recaudos=await filas_por_ids(db, ids))


async def _consignaciones_out(db: AsyncSession, consignaciones: list[Consignacion]) -> list[ConsignacionOut]:
    ids = [c.id for c in consignaciones]
    resumen: dict[uuid.UUID, tuple[int, Decimal]] = {}
    if ids:
        for cid, n, suma in await db.execute(
            select(ConsignacionRecaudo.consignacion_id, func.count(), func.sum(ConsignacionRecaudo.valor_aplicado))
            .where(ConsignacionRecaudo.consignacion_id.in_(ids))
            .group_by(ConsignacionRecaudo.consignacion_id)
        ):
            resumen[cid] = (n, suma)
    nombres = await _nombres(db, {c.usuario_consigna_id for c in consignaciones})
    return [
        ConsignacionOut(
            id=c.id,
            consecutivo=c.consecutivo,
            fecha_consignacion=c.fecha_consignacion,
            banco_destino=c.banco_destino,
            referencia_bancaria=c.referencia_bancaria,
            valor_consignado=c.valor_consignado,
            valor_aplicado=resumen.get(c.id, (0, Decimal(0)))[1],
            usuario_consigna_id=c.usuario_consigna_id,
            usuario_consigna=nombres.get(c.usuario_consigna_id, ""),
            estado=c.estado,
            aprobada_at=c.aprobada_at,
            verificada_at=c.verificada_at,
            observaciones=c.observaciones,
            cantidad_recaudos=resumen.get(c.id, (0, Decimal(0)))[0],
        )
        for c in consignaciones
    ]


async def listar_consignaciones(
    db: AsyncSession, actor: Actor, *, estado: EstadoConsignacion | None = None, limite: int = 50
) -> list[ConsignacionOut]:
    exigir(actor, PUEDE_VER_MOVIMIENTOS, "consultar las consignaciones")
    q = select(Consignacion).order_by(Consignacion.fecha_consignacion.desc(), Consignacion.consecutivo.desc())
    if estado:
        q = q.where(Consignacion.estado == estado)
    return await _consignaciones_out(db, list(await db.scalars(q.limit(min(limite, 200)))))


async def consignacion_out(db: AsyncSession, c: Consignacion) -> ConsignacionOut:
    return (await _consignaciones_out(db, [c]))[0]


async def detalle_consignacion(db: AsyncSession, actor: Actor, consignacion_id: uuid.UUID) -> ConsignacionDetalle:
    exigir(actor, PUEDE_VER_MOVIMIENTOS, "consultar las consignaciones")
    c = await db.get(Consignacion, consignacion_id)
    if c is None or c.tenant_id != actor.tenant_id:
        raise NoEncontrado("Consignación no encontrada")
    aplicaciones = list(
        await db.execute(
            select(ConsignacionRecaudo.recaudo_id, ConsignacionRecaudo.valor_aplicado).where(
                ConsignacionRecaudo.consignacion_id == c.id
            )
        )
    )
    filas = {f.id: f for f in await filas_por_ids(db, [rid for rid, _ in aplicaciones])}
    nombres = await _nombres(db, {u for u in (c.aprobada_por_id, c.verificada_por_id) if u})
    out = await consignacion_out(db, c)
    return ConsignacionDetalle(
        **out.model_dump(),
        # Un recaudo de otro auxiliar no es visible para quien consulta (RLS): se omite
        aplicaciones=[
            AplicacionDetalle(recaudo=filas[rid], valor_aplicado=v) for rid, v in aplicaciones if rid in filas
        ],
        soporte_url=_url_soporte(c.soporte_bancario_key, f"consignacion-{c.consecutivo}"),
        aprobada_por=nombres.get(c.aprobada_por_id) if c.aprobada_por_id else None,
        verificada_por=nombres.get(c.verificada_por_id) if c.verificada_por_id else None,
    )


# --- Dashboard ------------------------------------------------------------------------


async def dashboard(db: AsyncSession, actor: Actor, anio: int, mes: int) -> DashboardOut:
    """Totales vía la función SECURITY DEFINER resumen_recaudos: el Consejo ve agregados sin ver el detalle."""
    exigir(actor, PUEDE_VER_DASHBOARD, "consultar el dashboard de recaudos")
    if not (1 <= mes <= 12) or not (2000 <= anio <= 2100):
        raise ValidacionError("Periodo inválido")
    datos = await db.scalar(text("SELECT resumen_recaudos(:a, :m)"), {"a": anio, "m": mes})
    return DashboardOut.model_validate(datos)
