"""Fase 2: cierre de caja, entregas internas, conciliación bancaria y alertas."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest

from app.models import Recaudo
from app.models.enums import (
    EstadoAlerta,
    EstadoConsignacion,
    EstadoEntrega,
    EstadoRecaudo,
    MedioPago,
    SeveridadAlerta,
    TipoAlerta,
    UserRole,
)
from app.schemas.recaudos import (
    AplicacionIn,
    CierreCajaIn,
    ConsignacionCreate,
    EntregaConfirmacion,
    EntregaCreate,
    RecaudoCreate,
    RecaudoUpdate,
)
from app.services.notifications.email import recaudo_alerts
from app.services.recaudos import alertas, caja, conciliacion, service
from app.services.recaudos.dominio import (
    ActorSimple,
    PermisoDenegado,
    TransicionInvalida,
    ValidacionError,
)
from tests.integration.conftest import AHORA, Mundo

pytestmark = pytest.mark.integration
E = EstadoRecaudo


async def efectivo(m: Mundo, actor: ActorSimple, valor: int) -> Recaudo:
    otros = await m.concepto("OTROS")
    return await service.registrar_recaudo(
        m.db,
        actor,
        RecaudoCreate(
            concepto_id=otros.id,
            medio_pago=MedioPago.EFECTIVO,
            nombre_pagador="Visitante",
            valor_recibido=Decimal(valor),
        ),
        ahora=AHORA,
    )


async def efectivo_cerrado(m: Mundo, actor: ActorSimple, *valores: int) -> list[Recaudo]:
    """Registra el efectivo y cierra la caja cuadrada (con todo lo que el usuario tenga abierto)."""
    recaudos = [await efectivo(m, actor, v) for v in valores]
    resumen = await caja.estado_caja(m.db, actor, ahora=AHORA)
    await caja.cerrar_caja(m.db, actor, CierreCajaIn(valor_fisico_contado=resumen.total_efectivo), ahora=AHORA)
    return recaudos


def consignacion(ref: str, valor: int, *aplicaciones: tuple[uuid.UUID, int | None]) -> ConsignacionCreate:
    return ConsignacionCreate(
        fecha_consignacion=AHORA.date() - timedelta(days=1),
        banco_destino="Bancolombia",
        referencia_bancaria=ref,
        valor_consignado=Decimal(valor),
        aplicaciones=[
            AplicacionIn(recaudo_id=r, valor_aplicado=Decimal(v) if v is not None else None) for r, v in aplicaciones
        ],
    )


# --- Cierre de caja ----------------------------------------------------------------------


async def test_cierre_cuadrado_solo_cuenta_el_efectivo_propio_y_abierto(mundo: Mundo) -> None:
    auxiliar = await mundo.como(UserRole.AUXILIAR)
    a = await efectivo(mundo, auxiliar, 10000)
    b = await efectivo(mundo, auxiliar, 20000)
    otros = await mundo.concepto("OTROS")
    await service.registrar_recaudo(  # una transferencia no va a la caja
        mundo.db,
        auxiliar,
        RecaudoCreate(
            concepto_id=otros.id,
            medio_pago=MedioPago.TRANSFERENCIA,
            nombre_pagador="Apto 202",
            valor_recibido=Decimal(99000),
            numero_comprobante="T-1",
        ),
        ahora=AHORA,
    )
    admin = await mundo.como(UserRole.ADMIN)
    await efectivo(mundo, admin, 70000)  # efectivo de otra persona: tampoco

    auxiliar = await mundo.como(UserRole.AUXILIAR)
    resumen = await caja.estado_caja(mundo.db, auxiliar, ahora=AHORA)
    assert (resumen.cantidad, resumen.total_efectivo) == (2, Decimal(30000))

    cierre, generadas = await caja.cerrar_caja(
        mundo.db, auxiliar, CierreCajaIn(saldo_inicial=Decimal(50000), valor_fisico_contado=Decimal(80000)), ahora=AHORA
    )
    assert (cierre.tipo_diferencia, cierre.saldo_esperado_sistema, generadas) == ("CUADRADO", Decimal(80000), [])
    assert {a.cierre_id, b.cierre_id} == {cierre.id}
    assert (await caja.estado_caja(mundo.db, auxiliar, ahora=AHORA)).cantidad == 0

    # Tras el cierre, el auxiliar ya no puede editar esos recaudos
    with pytest.raises(PermisoDenegado, match="cierre de caja"):
        await service.editar_recaudo(
            mundo.db, auxiliar, a.id, RecaudoUpdate(observaciones="x", motivo="prueba de edición"), ahora=AHORA
        )


async def test_faltante_exige_justificacion_y_genera_alerta_critica(mundo: Mundo) -> None:
    auxiliar = await mundo.como(UserRole.AUXILIAR)
    await efectivo(mundo, auxiliar, 45000)
    with pytest.raises(ValidacionError, match="faltante de \\$5.000"):
        await caja.cerrar_caja(mundo.db, auxiliar, CierreCajaIn(valor_fisico_contado=Decimal(40000)), ahora=AHORA)

    cierre, generadas = await caja.cerrar_caja(
        mundo.db,
        auxiliar,
        CierreCajaIn(valor_fisico_contado=Decimal(40000), observacion_justificacion="Se devolvió mal un cambio"),
        ahora=AHORA,
    )
    assert cierre.tipo_diferencia == "FALTANTE"
    [alerta] = generadas
    assert (alerta.tipo, alerta.severidad, alerta.monto) == (
        TipoAlerta.DIFERENCIA_CIERRE,
        SeveridadAlerta.CRITICA,
        Decimal(5000),
    )


# --- Entregas internas ---------------------------------------------------------------


async def test_entrega_confirmada_pasa_el_efectivo_a_la_administracion(mundo: Mundo) -> None:
    auxiliar = await mundo.como(UserRole.AUXILIAR)
    abierto = await efectivo(mundo, auxiliar, 5000)
    with pytest.raises(ValidacionError, match="cierre primero"):
        await caja.crear_entrega(
            mundo.db, auxiliar, EntregaCreate(recibido_por_id=mundo.usuarios["ADMIN"], recaudo_ids=[abierto.id])
        )
    cerrados = await efectivo_cerrado(mundo, auxiliar, 30000, 20000)  # el cierre incluye también el abierto
    ids = [abierto.id, *(r.id for r in cerrados)]
    with pytest.raises(ValidacionError, match="administrador"):
        await caja.crear_entrega(
            mundo.db, auxiliar, EntregaCreate(recibido_por_id=mundo.usuarios["CONTABILIDAD"], recaudo_ids=ids)
        )
    entrega = await caja.crear_entrega(
        mundo.db, auxiliar, EntregaCreate(recibido_por_id=mundo.usuarios["ADMIN"], recaudo_ids=ids)
    )
    assert entrega.valor_total == Decimal(55000)

    otro_admin = await mundo.usuario("ADMIN2", "ADMIN")
    intruso = await mundo.como(UserRole.ADMIN, "ADMIN2")
    assert intruso.user_id == otro_admin
    with pytest.raises(PermisoDenegado, match="Solo quien recibe"):
        await caja.confirmar_entrega(mundo.db, intruso, entrega.id, EntregaConfirmacion(valor_contado=Decimal(55000)))

    admin = await mundo.como(UserRole.ADMIN)
    entrega, generadas = await caja.confirmar_entrega(
        mundo.db, admin, entrega.id, EntregaConfirmacion(valor_contado=Decimal(55000)), ahora=AHORA
    )
    assert (entrega.estado, generadas) == (EstadoEntrega.CONFIRMADA, [])
    for rid in ids:
        assert (await service.obtener_recaudo(mundo.db, admin, rid)).estado == E.ENTREGADO_ADMINISTRACION
    with pytest.raises(TransicionInvalida):
        await caja.rechazar_entrega(mundo.db, admin, entrega.id, "Intento tardío de rechazo")


async def test_entrega_con_descuadre_genera_alerta(mundo: Mundo) -> None:
    auxiliar = await mundo.como(UserRole.AUXILIAR)
    [r] = await efectivo_cerrado(mundo, auxiliar, 40000)
    entrega = await caja.crear_entrega(
        mundo.db, auxiliar, EntregaCreate(recibido_por_id=mundo.usuarios["ADMIN"], recaudo_ids=[r.id])
    )
    admin = await mundo.como(UserRole.ADMIN)
    with pytest.raises(ValidacionError, match="explique"):
        await caja.confirmar_entrega(mundo.db, admin, entrega.id, EntregaConfirmacion(valor_contado=Decimal(38000)))
    _, [alerta] = await caja.confirmar_entrega(
        mundo.db,
        admin,
        entrega.id,
        EntregaConfirmacion(valor_contado=Decimal(38000), observaciones="Faltan dos billetes de mil"),
    )
    assert (alerta.tipo, alerta.monto) == (TipoAlerta.DESCUADRE_ENTREGA, Decimal(2000))


async def test_entrega_rechazada_devuelve_el_efectivo_a_la_caja(mundo: Mundo) -> None:
    auxiliar = await mundo.como(UserRole.AUXILIAR)
    [r] = await efectivo_cerrado(mundo, auxiliar, 15000)
    datos = EntregaCreate(recibido_por_id=mundo.usuarios["ADMIN"], recaudo_ids=[r.id])
    entrega = await caja.crear_entrega(mundo.db, auxiliar, datos)
    admin = await mundo.como(UserRole.ADMIN)
    await caja.rechazar_entrega(mundo.db, admin, entrega.id, "No coincide con el sobre recibido")
    assert (await service.obtener_recaudo(mundo.db, admin, r.id)).entrega_id is None

    auxiliar = await mundo.como(UserRole.AUXILIAR)
    nueva = await caja.crear_entrega(mundo.db, auxiliar, datos)  # se puede volver a entregar
    assert nueva.consecutivo == entrega.consecutivo + 1


# --- Conciliación bancaria -----------------------------------------------------------


async def test_consignacion_parcial_en_dos_depositos(mundo: Mundo) -> None:
    admin = await mundo.como(UserRole.ADMIN)
    [r] = await efectivo_cerrado(mundo, admin, 50000)

    a, sin_alertas = await conciliacion.registrar_consignacion(
        mundo.db, admin, consignacion("REF-A", 30000, (r.id, 30000)), ahora=AHORA
    )
    assert sin_alertas == []
    [pendiente] = await conciliacion.pendientes_por_consignar(mundo.db, admin)
    assert pendiente.saldo == Decimal(20000)
    with pytest.raises(ValidacionError, match="solo le quedan \\$20.000"):
        await conciliacion.registrar_consignacion(mundo.db, admin, consignacion("REF-X", 25000, (r.id, 25000)))

    contabilidad = await mundo.como(UserRole.CONTABILIDAD)
    _, consignados = await conciliacion.aprobar_consignacion(mundo.db, contabilidad, a.id)
    assert consignados == []  # cubierto al 60 %: sigue pendiente

    admin = await mundo.como(UserRole.ADMIN)
    b, _ = await conciliacion.registrar_consignacion(
        mundo.db,
        admin,
        consignacion("REF-B", 20000, (r.id, None)),
        ahora=AHORA,  # None = todo el saldo
    )
    assert await conciliacion.pendientes_por_consignar(mundo.db, admin) == []

    contabilidad = await mundo.como(UserRole.CONTABILIDAD)
    _, consignados = await conciliacion.aprobar_consignacion(mundo.db, contabilidad, b.id)
    assert [x.id for x in consignados] == [r.id]
    assert r.estado == E.CONSIGNADO

    _, verificados = await conciliacion.verificar_consignacion(mundo.db, contabilidad, a.id)
    assert verificados == []  # falta verificar la otra parte
    _, verificados = await conciliacion.verificar_consignacion(mundo.db, contabilidad, b.id)
    assert [x.estado for x in verificados] == [E.VERIFICADO]


async def test_consignacion_descuadrada_genera_alerta_y_referencia_unica(mundo: Mundo) -> None:
    admin = await mundo.como(UserRole.ADMIN)
    [r] = await efectivo_cerrado(mundo, admin, 50000)
    c, [alerta] = await conciliacion.registrar_consignacion(
        mundo.db, admin, consignacion("REF-D", 48000, (r.id, None)), ahora=AHORA
    )
    assert (alerta.tipo, alerta.severidad, alerta.monto) == (
        TipoAlerta.DESCUADRE_CONSIGNACION,
        SeveridadAlerta.CRITICA,
        Decimal(2000),
    )
    with pytest.raises(ValidacionError, match="ya está registrada"):
        await conciliacion.registrar_consignacion(mundo.db, admin, consignacion("REF-D", 1000, (r.id, None)))
    assert c.estado == EstadoConsignacion.REGISTRADA


async def test_rechazar_consignacion_libera_el_saldo(mundo: Mundo) -> None:
    auxiliar = await mundo.como(UserRole.AUXILIAR)
    [r] = await efectivo_cerrado(mundo, auxiliar, 25000)
    c, _ = await conciliacion.registrar_consignacion(
        mundo.db, auxiliar, consignacion("REF-R", 25000, (r.id, None)), ahora=AHORA
    )
    with pytest.raises(PermisoDenegado):
        await conciliacion.aprobar_consignacion(mundo.db, auxiliar, c.id)

    admin = await mundo.como(UserRole.ADMIN)
    await conciliacion.rechazar_consignacion(mundo.db, admin, c.id, "El soporte bancario es ilegible")
    [pendiente] = await conciliacion.pendientes_por_consignar(mundo.db, admin)
    assert pendiente.saldo == Decimal(25000)
    with pytest.raises(TransicionInvalida):
        await conciliacion.aprobar_consignacion(mundo.db, admin, c.id)


async def test_no_se_consigna_efectivo_sin_cierre_ni_con_entrega_pendiente(mundo: Mundo) -> None:
    auxiliar = await mundo.como(UserRole.AUXILIAR)
    abierto = await efectivo(mundo, auxiliar, 8000)
    with pytest.raises(ValidacionError, match="cierre de caja"):
        await conciliacion.registrar_consignacion(mundo.db, auxiliar, consignacion("REF-1", 8000, (abierto.id, None)))
    await caja.cerrar_caja(mundo.db, auxiliar, CierreCajaIn(valor_fisico_contado=Decimal(8000)), ahora=AHORA)
    await caja.crear_entrega(
        mundo.db, auxiliar, EntregaCreate(recibido_por_id=mundo.usuarios["ADMIN"], recaudo_ids=[abierto.id])
    )
    with pytest.raises(ValidacionError, match="entrega interna sin confirmar"):
        await conciliacion.registrar_consignacion(mundo.db, auxiliar, consignacion("REF-2", 8000, (abierto.id, None)))


# --- Alertas ----------------------------------------------------------------------------


async def test_transferencias_viejas_generan_una_sola_alerta(mundo: Mundo) -> None:
    admin = await mundo.como(UserRole.ADMIN)
    otros = await mundo.concepto("OTROS")
    for dias in (5, 1):
        await service.registrar_recaudo(
            mundo.db,
            admin,
            RecaudoCreate(
                concepto_id=otros.id,
                medio_pago=MedioPago.TRANSFERENCIA,
                nombre_pagador="Apto 404",
                valor_recibido=Decimal(60000),
                numero_comprobante=f"T-{dias}",
                fecha_recaudo=AHORA - timedelta(days=dias),
            ),
            ahora=AHORA,
        )
    nuevas = await alertas.detectar_transferencias_sin_verificar(mundo.db, mundo.tenant, dias=3, ahora=AHORA)
    assert len(nuevas) == 1  # solo la de hace 5 días
    assert "más de 3 días" in nuevas[0].mensaje
    assert await alertas.detectar_transferencias_sin_verificar(mundo.db, mundo.tenant, dias=3, ahora=AHORA) == []


async def test_atender_alerta_exige_resolucion_y_rol_admin(mundo: Mundo) -> None:
    auxiliar = await mundo.como(UserRole.AUXILIAR)
    await efectivo(mundo, auxiliar, 10000)
    _, [alerta] = await caja.cerrar_caja(
        mundo.db,
        auxiliar,
        CierreCajaIn(valor_fisico_contado=Decimal(12000), observacion_justificacion="Un visitante no esperó el cambio"),
        ahora=AHORA,
    )
    assert alerta.severidad == SeveridadAlerta.ADVERTENCIA  # sobrante

    contabilidad = await mundo.como(UserRole.CONTABILIDAD)
    assert [a.id for a in await alertas.listar_alertas(mundo.db, contabilidad)] == [alerta.id]
    with pytest.raises(PermisoDenegado):
        await alertas.atender_alerta(mundo.db, contabilidad, alerta.id, "Revisado")

    admin = await mundo.como(UserRole.ADMIN)
    atendida = await alertas.atender_alerta(mundo.db, admin, alerta.id, "Se registró como ingreso por aprovechamiento")
    assert atendida.estado == EstadoAlerta.ATENDIDA
    assert await alertas.listar_alertas(mundo.db, admin) == []


def test_correo_de_alertas_destaca_las_criticas() -> None:
    asunto, texto, html = recaudo_alerts(
        tenant_name="Los Pinos",
        alertas=[("CRITICA", "Faltante de $5.000"), ("ADVERTENCIA", "Transferencia sin verificar")],
        url="https://app.test/los-pinos/recaudos/alertas",
    )
    assert asunto.startswith("⚠ 2 alertas")
    assert "[Crítica] Faltante de $5.000" in texto
    assert "#b42318" in html
