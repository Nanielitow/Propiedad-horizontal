"""Casos de uso de recaudos: registrar, editar, anular, verificar e historial.

El servicio recibe una sesión que YA tiene el contexto RLS del usuario (lo fija
la dependencia de la API) y nunca hace commit: el endpoint confirma la
transacción. Así un recaudo, su desglose y su auditoría se guardan juntos o no
se guarda nada.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AlertaRecaudo,
    AuditoriaRecaudo,
    ConceptoRecaudo,
    Recaudo,
    RecaudoItem,
    RecaudoParqueadero,
    Reserva,
    Unit,
    ZonaSocial,
)
from app.models.enums import (
    EstadoRecaudo,
    EstadoReserva,
    MedioPago,
    SeveridadAlerta,
    TipoAlerta,
    TipoCobro,
    UserRole,
)
from app.schemas.recaudos import CotizacionParqueadero, ItemIn, RecaudoCreate, RecaudoUpdate
from app.services.recaudos.alertas import crear_alerta
from app.services.recaudos.dominio import (
    ANULACION_REQUIERE_ALERTA,
    PUEDE_ANULAR,
    PUEDE_EDITAR,
    PUEDE_REGISTRAR,
    PUEDE_VER_AUDITORIA,
    PUEDE_VERIFICAR,
    Actor,
    NoEncontrado,
    PermisoDenegado,
    TransicionInvalida,
    ValidacionError,
    calcular_parqueadero,
    es_mismo_dia_bogota,
    exigir,
    pesos,
    validar_soporte,
    validar_transicion,
    valor_por_defecto,
)

E = EstadoRecaudo
# Tolerancia para relojes desfasados entre el navegador y el servidor
_MARGEN_FUTURO = timedelta(minutes=5)
_SET_MOTIVO = text("SELECT set_config('app.motivo', :m, true)")


def _ahora(ahora: datetime | None) -> datetime:
    return ahora or datetime.now(UTC)


async def _motivo(db: AsyncSession, motivo: str | None) -> None:
    """El trigger de auditoría lee app.motivo (local a la transacción)."""
    await db.execute(_SET_MOTIVO, {"m": motivo or ""})


async def _concepto(db: AsyncSession, actor: Actor, concepto_id: uuid.UUID) -> ConceptoRecaudo:
    concepto = await db.get(ConceptoRecaudo, concepto_id)
    if concepto is None or concepto.tenant_id != actor.tenant_id:
        raise NoEncontrado("Concepto de recaudo no encontrado")
    if not concepto.activo:
        raise ValidacionError(f"El concepto «{concepto.nombre}» está inactivo")
    return concepto


async def obtener_recaudo(db: AsyncSession, actor: Actor, recaudo_id: uuid.UUID) -> Recaudo:
    # RLS ya oculta los recaudos que el rol no puede ver (p. ej. los de otro auxiliar)
    recaudo = await db.get(Recaudo, recaudo_id)
    if recaudo is None or recaudo.tenant_id != actor.tenant_id:
        raise NoEncontrado("Recaudo no encontrado")
    return recaudo


async def cotizar_parqueadero(
    db: AsyncSession, actor: Actor, concepto_id: uuid.UUID, ingreso: datetime, salida: datetime
) -> CotizacionParqueadero:
    concepto = await _concepto(db, actor, concepto_id)
    if not concepto.requiere_vehiculo:
        raise ValidacionError(f"«{concepto.nombre}» no es un concepto de parqueadero")
    if concepto.tipo_cobro != TipoCobro.POR_HORA or concepto.tarifa_base is None or not concepto.fraccion_minutos:
        tarifa = concepto.tarifa_base or Decimal(0)
        minutos = max(1, int((salida - ingreso).total_seconds() // 60))
        return CotizacionParqueadero(minutos=minutos, fracciones=1, tarifa_sugerida=tarifa)
    calc = calcular_parqueadero(ingreso, salida, concepto.tarifa_base, concepto.fraccion_minutos)
    return CotizacionParqueadero(minutos=calc.minutos, fracciones=calc.fracciones, tarifa_sugerida=calc.tarifa_sugerida)


async def _desglose_de_reserva(
    db: AsyncSession, actor: Actor, concepto: ConceptoRecaudo, reserva: Reserva
) -> list[ItemIn]:
    """Sin desglose explícito, un alquiler se cobra con las tarifas de la zona: alquiler + aseo."""
    zona = await db.get(ZonaSocial, reserva.zona_id)
    alquiler = (zona.tarifa_alquiler if zona else None) or concepto.tarifa_base
    if not alquiler:
        raise ValidacionError("Indique el valor del alquiler: la zona no tiene tarifa configurada")
    items = [ItemIn(concepto_id=concepto.id, valor=alquiler, descripcion="Valor alquiler")]
    if zona and zona.tarifa_aseo:
        aseo = await db.scalar(
            select(ConceptoRecaudo).where(
                ConceptoRecaudo.tenant_id == actor.tenant_id,
                ConceptoRecaudo.codigo == "ASEO",
                ConceptoRecaudo.activo,
            )
        )
        if aseo is None:
            raise ValidacionError("La zona cobra aseo, pero el concepto ASEO no existe o está inactivo")
        items.append(ItemIn(concepto_id=aseo.id, valor=zona.tarifa_aseo, descripcion="Valor aseo"))
    return items


async def registrar_recaudo(
    db: AsyncSession, actor: Actor, data: RecaudoCreate, *, ahora: datetime | None = None
) -> Recaudo:
    exigir(actor, PUEDE_REGISTRAR, "registrar recaudos")
    ahora = _ahora(ahora)
    concepto = await _concepto(db, actor, data.concepto_id)

    fecha = data.fecha_recaudo or ahora
    if fecha.tzinfo is None:
        raise ValidacionError("La fecha del recaudo debe incluir zona horaria")
    if fecha > ahora + _MARGEN_FUTURO:
        raise ValidacionError("La fecha del recaudo no puede estar en el futuro")

    if data.unidad_id is not None:
        unidad = await db.get(Unit, data.unidad_id)
        if unidad is None or unidad.tenant_id != actor.tenant_id:
            raise NoEncontrado("Unidad no encontrada")

    # --- Campos dinámicos: parqueadero ---------------------------------------
    sugerido: Decimal | None = None
    if concepto.requiere_vehiculo:
        if data.parqueadero is None:
            raise ValidacionError("El parqueadero requiere placa, hora de ingreso y hora de salida")
        if data.parqueadero.hora_salida > ahora + _MARGEN_FUTURO:
            raise ValidacionError("La hora de salida no puede estar en el futuro")
        cotizacion = await cotizar_parqueadero(
            db, actor, concepto.id, data.parqueadero.hora_ingreso, data.parqueadero.hora_salida
        )
        sugerido = cotizacion.tarifa_sugerida
    elif data.parqueadero is not None:
        raise ValidacionError(f"«{concepto.nombre}» no lleva datos de vehículo")

    # --- Campos dinámicos: alquiler de zonas ---------------------------------
    reserva: Reserva | None = None
    if data.reserva_id is not None:
        reserva = await db.get(Reserva, data.reserva_id)
        if reserva is None or reserva.tenant_id != actor.tenant_id:
            raise NoEncontrado("Reserva no encontrada")
        if reserva.estado == EstadoReserva.CANCELADA:
            raise ValidacionError("La reserva está cancelada")
    elif concepto.requiere_reserva:
        raise ValidacionError(f"«{concepto.nombre}» debe vincularse a una reserva")

    # --- Desglose y valor ----------------------------------------------------
    items = list(data.desglose or [])
    if not items and reserva is not None and concepto.requiere_reserva and data.valor_recibido is None:
        items = await _desglose_de_reserva(db, actor, concepto, reserva)

    if items:
        ids = {i.concepto_id for i in items}
        if concepto.id not in ids:
            raise ValidacionError("El desglose debe incluir el concepto principal del recaudo")
        validos = set(
            await db.scalars(select(ConceptoRecaudo.id).where(ConceptoRecaudo.id.in_(ids), ConceptoRecaudo.activo))
        )
        if validos != ids:
            raise ValidacionError("El desglose contiene conceptos inexistentes o inactivos")
        suma = sum((i.valor for i in items), Decimal(0))
        valor = data.valor_recibido or suma
        if valor != suma:
            raise ValidacionError(f"La suma del desglose ({suma}) no coincide con el valor recibido ({valor})")
    else:
        valor_o_none = data.valor_recibido or sugerido or valor_por_defecto(concepto.tipo_cobro, concepto.tarifa_base)
        if valor_o_none is None or valor_o_none <= 0:
            raise ValidacionError("Indique el valor recibido")
        valor = valor_o_none
        items = [ItemIn(concepto_id=concepto.id, valor=valor)]

    # --- Soportes ---------------------------------------------------------------
    validar_soporte(actor, data.soporte_key)
    if data.medio_pago != MedioPago.EFECTIVO and not (data.numero_comprobante or data.soporte_key):
        raise ValidacionError("Las transferencias y consignaciones requieren número de comprobante o soporte adjunto")

    await _motivo(db, None)
    recaudo = Recaudo(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        fecha_recaudo=fecha,
        concepto_id=concepto.id,
        valor_recibido=valor,
        nombre_pagador=data.nombre_pagador,
        identificacion_pagador=data.identificacion_pagador,
        unidad_id=data.unidad_id,
        medio_pago=data.medio_pago,
        numero_comprobante=data.numero_comprobante,
        soporte_key=data.soporte_key,
        observaciones=data.observaciones,
        reserva_id=data.reserva_id,
        usuario_receptor_id=actor.user_id,
    )
    db.add(recaudo)
    # Primero el recaudo (el trigger asigna consecutivo y estado) y luego sus
    # detalles: las FK compuestas no las conoce el ORM, así que el orden es explícito.
    await db.flush()
    db.add_all(
        RecaudoItem(
            id=uuid.uuid4(),
            tenant_id=actor.tenant_id,
            recaudo_id=recaudo.id,
            concepto_id=i.concepto_id,
            valor=i.valor,
            descripcion=i.descripcion,
        )
        for i in items
    )
    if data.parqueadero is not None and sugerido is not None:
        db.add(
            RecaudoParqueadero(
                recaudo_id=recaudo.id,
                tenant_id=actor.tenant_id,
                placa_vehiculo=data.parqueadero.placa_vehiculo,
                hora_ingreso=data.parqueadero.hora_ingreso,
                hora_salida=data.parqueadero.hora_salida,
                tarifa_sugerida=sugerido,
            )
        )
    await db.flush()
    return recaudo


async def editar_recaudo(
    db: AsyncSession, actor: Actor, recaudo_id: uuid.UUID, data: RecaudoUpdate, *, ahora: datetime | None = None
) -> Recaudo:
    exigir(actor, PUEDE_EDITAR, "editar recaudos")
    recaudo = await obtener_recaudo(db, actor, recaudo_id)
    if recaudo.estado in (E.VERIFICADO, E.ANULADO):
        raise ValidacionError(f"Un recaudo {recaudo.estado.value.lower()} no se puede editar")
    if actor.role == UserRole.AUXILIAR:
        if recaudo.cierre_id is not None:
            raise PermisoDenegado("El recaudo ya está en un cierre de caja: solicite el cambio a la administración")
        if not es_mismo_dia_bogota(recaudo.fecha_recaudo, _ahora(ahora)):
            raise PermisoDenegado("Solo puede editar sus recaudos del mismo día")

    cambios = data.model_dump(exclude_unset=True, exclude={"motivo"})
    if not cambios:
        raise ValidacionError("No hay cambios para guardar")
    if "nombre_pagador" in cambios and not cambios["nombre_pagador"]:
        raise ValidacionError("El nombre del pagador es obligatorio")
    validar_soporte(actor, cambios.get("soporte_key"))
    if cambios.get("unidad_id") is not None:
        unidad = await db.get(Unit, cambios["unidad_id"])
        if unidad is None or unidad.tenant_id != actor.tenant_id:
            raise NoEncontrado("Unidad no encontrada")

    await _motivo(db, data.motivo)
    for campo, valor in cambios.items():
        setattr(recaudo, campo, valor)
    await db.flush()
    await _motivo(db, None)
    return recaudo


async def anular_recaudo(
    db: AsyncSession, actor: Actor, recaudo_id: uuid.UUID, motivo: str, *, ahora: datetime | None = None
) -> Recaudo:
    return (await anular_recaudo_con_alertas(db, actor, recaudo_id, motivo, ahora=ahora))[0]


async def anular_recaudo_con_alertas(
    db: AsyncSession, actor: Actor, recaudo_id: uuid.UUID, motivo: str, *, ahora: datetime | None = None
) -> tuple[Recaudo, list[AlertaRecaudo]]:
    exigir(actor, PUEDE_ANULAR, "anular recaudos")
    motivo = motivo.strip()
    if len(motivo) < 10:
        raise ValidacionError("El motivo de la anulación debe tener al menos 10 caracteres")
    recaudo = await obtener_recaudo(db, actor, recaudo_id)
    estado_previo = recaudo.estado
    try:
        validar_transicion(estado_previo, E.ANULADO)
    except TransicionInvalida as exc:
        raise TransicionInvalida("El recaudo ya está anulado") from exc

    await _motivo(db, motivo)
    recaudo.estado = E.ANULADO
    recaudo.anulado_por_id = actor.user_id
    recaudo.anulado_at = _ahora(ahora)
    recaudo.motivo_anulacion = motivo
    await db.flush()
    await _motivo(db, None)

    alertas: list[AlertaRecaudo] = []
    if estado_previo in ANULACION_REQUIERE_ALERTA:
        alerta = await crear_alerta(
            db,
            actor.tenant_id,
            tipo=TipoAlerta.ANULACION_POSTERIOR,
            severidad=SeveridadAlerta.CRITICA,
            entidad="recaudo",
            entidad_id=recaudo.id,
            mensaje=(
                f"Se anuló el recaudo #{recaudo.consecutivo} por {pesos(recaudo.valor_recibido)} cuando ya estaba "
                f"{estado_previo.value.replace('_', ' ').lower()}. Motivo: {motivo}"
            ),
            monto=recaudo.valor_recibido,
        )
        alertas.append(alerta)
    return recaudo, alertas


async def verificar_recaudo(
    db: AsyncSession, actor: Actor, recaudo_id: uuid.UUID, *, ahora: datetime | None = None
) -> Recaudo:
    """Verifica una transferencia o consignación directa encontrada en el extracto.

    El efectivo se verifica al conciliar la consignación bancaria que lo contiene.
    """
    exigir(actor, PUEDE_VERIFICAR, "verificar recaudos")
    recaudo = await obtener_recaudo(db, actor, recaudo_id)
    if recaudo.estado != E.PENDIENTE_VERIFICACION:
        raise TransicionInvalida(
            "Solo se verifican aquí transferencias pendientes; el efectivo se verifica al conciliar su consignación"
        )
    await _motivo(db, None)
    recaudo.estado = E.VERIFICADO
    recaudo.verificado_por_id = actor.user_id
    recaudo.verificado_at = _ahora(ahora)
    await db.flush()
    return recaudo


async def historial_recaudo(db: AsyncSession, actor: Actor, recaudo_id: uuid.UUID) -> list[AuditoriaRecaudo]:
    exigir(actor, PUEDE_VER_AUDITORIA, "consultar la auditoría")
    await obtener_recaudo(db, actor, recaudo_id)
    rows = await db.scalars(
        select(AuditoriaRecaudo)
        .where(AuditoriaRecaudo.recaudo_id == recaudo_id)
        .order_by(AuditoriaRecaudo.fecha_hora, AuditoriaRecaudo.id)
    )
    return list(rows)
