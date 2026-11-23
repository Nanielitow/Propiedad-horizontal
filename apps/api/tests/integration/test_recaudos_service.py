"""Casos de uso del servicio de recaudos contra la base de datos real.

Sesión async como app_user dentro de una transacción que se revierte al final.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.models import AlertaRecaudo, RecaudoItem, RecaudoParqueadero
from app.models.enums import AccionAuditoria, EstadoRecaudo, MedioPago, TipoAlerta, UserRole
from app.schemas.recaudos import ParqueaderoIn, RecaudoCreate, RecaudoUpdate
from app.services.recaudos import service
from app.services.recaudos.dominio import ActorSimple, PermisoDenegado, TransicionInvalida, ValidacionError
from tests.integration.conftest import AHORA, Mundo

pytestmark = pytest.mark.integration


async def _transferencia(m: Mundo, actor: ActorSimple, valor: int = 80000) -> uuid.UUID:
    otros = await m.concepto("OTROS")
    r = await service.registrar_recaudo(
        m.db,
        actor,
        RecaudoCreate(
            concepto_id=otros.id,
            medio_pago=MedioPago.TRANSFERENCIA,
            nombre_pagador="Apto 301",
            valor_recibido=Decimal(valor),
            numero_comprobante="NEQUI-998877",
        ),
        ahora=AHORA,
    )
    return r.id


async def test_parqueadero_calcula_tarifa_y_normaliza_placa(mundo: Mundo) -> None:
    auxiliar = await mundo.como(UserRole.AUXILIAR)
    parqueadero = await mundo.concepto("PARQUEADERO")
    r = await service.registrar_recaudo(
        mundo.db,
        auxiliar,
        RecaudoCreate(
            concepto_id=parqueadero.id,
            medio_pago=MedioPago.EFECTIVO,
            nombre_pagador="Visitante torre 2",
            parqueadero=ParqueaderoIn(
                placa_vehiculo="abc-123", hora_ingreso=AHORA - timedelta(minutes=61), hora_salida=AHORA
            ),
        ),
        ahora=AHORA,
    )
    assert (r.consecutivo, r.estado, r.valor_recibido) == (1, EstadoRecaudo.RECAUDADO_EN_CAJA, Decimal("4000.00"))
    detalle = await mundo.db.get(RecaudoParqueadero, r.id)
    assert detalle is not None
    assert (detalle.placa_vehiculo, detalle.minutos_totales) == ("ABC123", 61)
    await mundo.db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))  # el desglose automático cuadra


async def test_parqueadero_sin_placa_es_rechazado(mundo: Mundo) -> None:
    admin = await mundo.como(UserRole.ADMIN)
    parqueadero = await mundo.concepto("PARQUEADERO")
    with pytest.raises(ValidacionError, match="placa"):
        await service.registrar_recaudo(
            mundo.db,
            admin,
            RecaudoCreate(concepto_id=parqueadero.id, medio_pago=MedioPago.EFECTIVO, nombre_pagador="Visitante"),
            ahora=AHORA,
        )


async def test_alquiler_se_desglosa_en_alquiler_y_aseo(mundo: Mundo) -> None:
    admin = await mundo.como(UserRole.ADMIN)
    zona = await mundo.db.scalar(
        text(
            "INSERT INTO zonas_sociales (tenant_id, nombre, tarifa_alquiler, tarifa_aseo)"
            " VALUES (:t, 'Salón social', 150000, 50000) RETURNING id"
        ),
        {"t": mundo.tenant},
    )
    reserva = await mundo.db.scalar(
        text(
            "INSERT INTO reservas (tenant_id, zona_id, solicitante, fecha_evento, estado)"
            " VALUES (:t, :z, 'Familia Pérez', current_date + 3, 'CONFIRMADA') RETURNING id"
        ),
        {"t": mundo.tenant, "z": zona},
    )
    alquiler = await mundo.concepto("ALQUILER_ZONA")
    datos = {"concepto_id": alquiler.id, "medio_pago": MedioPago.EFECTIVO, "nombre_pagador": "Familia Pérez"}

    with pytest.raises(ValidacionError, match="reserva"):
        await service.registrar_recaudo(mundo.db, admin, RecaudoCreate(**datos), ahora=AHORA)

    r = await service.registrar_recaudo(mundo.db, admin, RecaudoCreate(**datos, reserva_id=reserva), ahora=AHORA)
    items = (await mundo.db.scalars(select(RecaudoItem).where(RecaudoItem.recaudo_id == r.id))).all()
    assert r.valor_recibido == Decimal("200000.00")
    assert sorted((i.descripcion, i.valor) for i in items) == [
        ("Valor alquiler", Decimal("150000.00")),
        ("Valor aseo", Decimal("50000.00")),
    ]
    await mundo.db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


async def test_desglose_manual_debe_sumar_el_valor(mundo: Mundo) -> None:
    admin = await mundo.como(UserRole.ADMIN)
    otros = await mundo.concepto("OTROS")
    with pytest.raises(ValidacionError, match="no coincide"):
        await service.registrar_recaudo(
            mundo.db,
            admin,
            RecaudoCreate(
                concepto_id=otros.id,
                medio_pago=MedioPago.EFECTIVO,
                nombre_pagador="Proveedor",
                valor_recibido=Decimal(100000),
                desglose=[{"concepto_id": otros.id, "valor": Decimal(90000)}],
            ),
            ahora=AHORA,
        )


async def test_transferencia_exige_comprobante(mundo: Mundo) -> None:
    admin = await mundo.como(UserRole.ADMIN)
    otros = await mundo.concepto("OTROS")
    with pytest.raises(ValidacionError, match="comprobante"):
        await service.registrar_recaudo(
            mundo.db,
            admin,
            RecaudoCreate(
                concepto_id=otros.id,
                medio_pago=MedioPago.TRANSFERENCIA,
                nombre_pagador="Apto 301",
                valor_recibido=Decimal(80000),
            ),
            ahora=AHORA,
        )


async def test_fecha_futura_rechazada(mundo: Mundo) -> None:
    admin = await mundo.como(UserRole.ADMIN)
    aseo = await mundo.concepto("ASEO")
    with pytest.raises(ValidacionError, match="futuro"):
        await service.registrar_recaudo(
            mundo.db,
            admin,
            RecaudoCreate(
                concepto_id=aseo.id,
                medio_pago=MedioPago.EFECTIVO,
                nombre_pagador="Apto 101",
                fecha_recaudo=AHORA + timedelta(days=1),
            ),
            ahora=AHORA,
        )


async def test_contabilidad_no_registra(mundo: Mundo) -> None:
    contabilidad = await mundo.como(UserRole.CONTABILIDAD)
    with pytest.raises(PermisoDenegado):
        await _transferencia(mundo, contabilidad)


async def test_auxiliar_no_anula_y_admin_si_con_auditoria(mundo: Mundo) -> None:
    auxiliar = await mundo.como(UserRole.AUXILIAR)
    rid = await _transferencia(mundo, auxiliar)
    with pytest.raises(PermisoDenegado):
        await service.anular_recaudo(mundo.db, auxiliar, rid, "Me equivoqué de concepto")

    admin = await mundo.como(UserRole.ADMIN)
    r = await service.anular_recaudo(mundo.db, admin, rid, "Se registró con el concepto equivocado", ahora=AHORA)
    assert r.estado == EstadoRecaudo.ANULADO
    with pytest.raises(TransicionInvalida, match="ya está anulado"):
        await service.anular_recaudo(mundo.db, admin, rid, "Segundo intento de anulación")

    historial = await service.historial_recaudo(mundo.db, admin, rid)
    assert [h.accion for h in historial] == [AccionAuditoria.CREACION, AccionAuditoria.ANULACION]
    assert historial[-1].motivo == "Se registró con el concepto equivocado"


async def test_anular_lo_ya_verificado_genera_alerta_critica(mundo: Mundo) -> None:
    admin = await mundo.como(UserRole.ADMIN)
    rid = await _transferencia(mundo, admin)
    contabilidad = await mundo.como(UserRole.CONTABILIDAD)
    verificado = await service.verificar_recaudo(mundo.db, contabilidad, rid, ahora=AHORA)
    assert verificado.estado == EstadoRecaudo.VERIFICADO
    with pytest.raises(TransicionInvalida):
        await service.verificar_recaudo(mundo.db, contabilidad, rid)

    admin = await mundo.como(UserRole.ADMIN)
    await service.anular_recaudo(mundo.db, admin, rid, "El banco reversó la transferencia", ahora=AHORA)
    alerta = (await mundo.db.scalars(select(AlertaRecaudo).where(AlertaRecaudo.entidad_id == rid))).one()
    assert alerta.tipo == TipoAlerta.ANULACION_POSTERIOR
    assert alerta.monto == Decimal("80000.00")


async def test_auxiliar_edita_solo_el_mismo_dia(mundo: Mundo) -> None:
    auxiliar = await mundo.como(UserRole.AUXILIAR)
    rid = await _transferencia(mundo, auxiliar)
    cambio = RecaudoUpdate(observaciones="Pagó en dos partes", motivo="Aclaración del pago")
    with pytest.raises(PermisoDenegado, match="mismo día"):
        await service.editar_recaudo(mundo.db, auxiliar, rid, cambio, ahora=AHORA + timedelta(days=1))
    r = await service.editar_recaudo(mundo.db, auxiliar, rid, cambio, ahora=AHORA)
    assert r.observaciones == "Pagó en dos partes"
