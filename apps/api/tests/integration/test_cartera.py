"""Fase 1 de la cartera: facturación, intereses, pagos, descuentos, anulaciones, paz y salvo,
triggers y RLS contra la base real."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models import AjusteCartera, CargoCartera, ConceptoCartera, PagoCartera, SaldoCargo
from app.models.enums import EstadoPagoCartera, MedioPago, MetodoCuota, RelacionUnidad, TipoAjuste, TipoUnidad, UserRole
from app.schemas.cartera import AjusteIn, CargoManualIn, ConfigIn, EmitirPeriodoIn, PagoIn
from app.schemas.unidades import PersonaIn, UnidadIn, VinculoIn
from app.services.cartera import cargos, comun, facturacion, pagos, paz_y_salvo
from app.services.comun import PermisoDenegado, ValidacionError, hoy_bogota
from app.services.unidades import gestion
from tests.integration.conftest import Mundo

A = UserRole.ADMIN
D = Decimal
HOY = hoy_bogota()
MES_PASADO = (HOY.replace(day=1) - timedelta(days=1)).replace(day=1)
MES_SIGUIENTE = (HOY.replace(day=28) + timedelta(days=5)).replace(day=1)


@pytest.fixture
async def conjunto(mundo: Mundo) -> dict[str, uuid.UUID]:
    """Dos apartamentos (60 % y 40 %), un parqueadero anexo sin coeficiente y un local sin coeficiente."""
    await mundo.db.execute(text("SELECT seed_conceptos_cartera(:t)"), {"t": mundo.tenant})
    admin = await mundo.como(A)
    residente = await mundo.usuario("RESIDENTE", "RESIDENTE")
    admin = await mundo.como(A)
    a = await gestion.crear_unidad(mundo.db, admin, UnidadIn(tower="1", number="101", coefficient=D("60")))
    b = await gestion.crear_unidad(mundo.db, admin, UnidadIn(tower="1", number="102", coefficient=D("40")))
    await gestion.crear_unidad(
        mundo.db, admin, UnidadIn(tower="1", number="PQ-1", tipo=TipoUnidad.PARQUEADERO, unidad_principal_id=a.id)
    )
    local = await gestion.crear_unidad(mundo.db, admin, UnidadIn(number="L-1", tipo=TipoUnidad.LOCAL))
    await gestion.vincular(
        mundo.db,
        admin,
        a.id,
        VinculoIn(
            persona=PersonaIn(nombre_completo="Ana Propietaria", user_id=residente), relacion=RelacionUnidad.PROPIETARIO
        ),
    )
    await comun.guardar_config(
        mundo.db,
        admin,
        ConfigIn(
            metodo=MetodoCuota.COEFICIENTE,
            presupuesto_mensual=D("1000000"),
            dia_vencimiento=10,
            tasa_mora_mensual=D("1.5"),
        ),
    )
    return {"a": a.id, "b": b.id, "local": local.id}


async def _emitir(m: Mundo, mes: date, emision: date | None = None) -> None:
    admin = await m.como(A)
    await facturacion.emitir(m.db, admin, EmitirPeriodoIn(anio=mes.year, mes=mes.month, fecha_emision=emision))


async def _saldo(m: Mundo, unidad: uuid.UUID) -> Decimal:
    return await comun.saldo_unidad(m.db, unidad)


async def _pagar(m: Mundo, unidad: uuid.UUID, valor: str, fecha: date = HOY, **extra: object) -> pagos.ResultadoPago:
    admin = await m.como(A)
    return await pagos.registrar_pago(
        m.db,
        admin,
        PagoIn(
            unidad_id=unidad,
            fecha_pago=fecha,
            valor=D(valor),
            medio_pago=extra.pop("medio", MedioPago.EFECTIVO),
            **extra,
        ),  # type: ignore[arg-type]
    )


# --- Facturación -------------------------------------------------------------------


async def test_sin_configuracion_no_se_factura(mundo: Mundo) -> None:
    await mundo.db.execute(text("SELECT seed_conceptos_cartera(:t)"), {"t": mundo.tenant})
    admin = await mundo.como(A)
    with pytest.raises(ValidacionError, match="Configure primero"):
        await facturacion.prefacturar(mundo.db, admin, EmitirPeriodoIn(anio=HOY.year, mes=HOY.month))


async def test_emitir_por_coeficiente(mundo: Mundo, conjunto: dict[str, uuid.UUID]) -> None:
    admin = await mundo.como(A)
    pf = await facturacion.prefacturar(mundo.db, admin, EmitirPeriodoIn(anio=HOY.year, mes=HOY.month))
    assert {ln.unidad.etiqueta: ln.cuota for ln in pf.lineas} == {"1-101": D("600000"), "1-102": D("400000")}
    assert any("L-1" in a for a in pf.advertencias)  # el local no tiene coeficiente
    assert any("sin propietario" in a for a in pf.advertencias)  # el 1-102
    await _emitir(mundo, HOY)
    c = (await mundo.db.scalars(select(CargoCartera).where(CargoCartera.unidad_id == conjunto["a"]))).one()
    assert c.responsable_nombre == "Ana Propietaria" and c.valor == D("600000")
    assert await _saldo(mundo, conjunto["a"]) == D("600000")
    with pytest.raises(ValidacionError, match="ya fue emitido"):
        await _emitir(mundo, HOY)


async def test_tarifa_por_tipo(mundo: Mundo, conjunto: dict[str, uuid.UUID]) -> None:
    admin = await mundo.como(A)
    await comun.guardar_config(
        mundo.db,
        admin,
        ConfigIn(
            metodo=MetodoCuota.TARIFA_POR_TIPO,
            tarifas_por_tipo={TipoUnidad.APARTAMENTO: D("250000"), TipoUnidad.LOCAL: D("180000")},
        ),
    )
    pf = await facturacion.prefacturar(mundo.db, admin, EmitirPeriodoIn(anio=HOY.year, mes=HOY.month))
    assert sorted(ln.cuota for ln in pf.lineas) == [
        D("180000"),
        D("250000"),
        D("250000"),
    ]  # el parqueadero no tiene tarifa


async def test_intereses_sobre_capital_vencido(mundo: Mundo, conjunto: dict[str, uuid.UUID]) -> None:
    await _emitir(mundo, MES_PASADO, emision=MES_PASADO)  # vence el día 10 del mes pasado
    await _pagar(mundo, conjunto["b"], "400000", fecha=MES_PASADO)  # el 102 pagó a tiempo
    await _emitir(mundo, HOY)
    filas = (
        await mundo.db.execute(
            select(CargoCartera.unidad_id, CargoCartera.valor)
            .join(ConceptoCartera, ConceptoCartera.id == CargoCartera.concepto_id)
            .where(ConceptoCartera.codigo == "INTERESES_MORA")
        )
    ).all()
    assert filas == [(conjunto["a"], D("9000"))]  # 1,5 % de 600.000; el 102 no debe intereses
    assert await _saldo(mundo, conjunto["a"]) == D("1209000")


# --- Pagos ---------------------------------------------------------------------------


async def test_pago_imputa_por_ley_y_deja_saldo_a_favor(mundo: Mundo, conjunto: dict[str, uuid.UUID]) -> None:
    await _emitir(mundo, MES_PASADO, emision=MES_PASADO)
    await _emitir(mundo, HOY)  # 101 debe 600.000 + 600.000 + 9.000 de intereses
    r = await _pagar(mundo, conjunto["a"], "615000")
    cargos_ = {
        c.id: c for c in await mundo.db.scalars(select(CargoCartera).where(CargoCartera.unidad_id == conjunto["a"]))
    }
    orden = [(cargos_[cid].descripcion.split()[0], v) for cid, v in r.imputacion.aplicaciones]
    assert orden == [("Intereses", D("9000")), ("Cuota", D("600000")), ("Cuota", D("6000"))]
    assert r.saldo_pendiente == D("594000")
    assert r.pago.consecutivo >= 1

    # Pago mayor a la deuda: el sobrante queda a favor y cubre la siguiente facturación
    await _pagar(mundo, conjunto["a"], "700000")
    assert await _saldo(mundo, conjunto["a"]) == 0
    favor = await comun.saldos_a_favor(mundo.db, conjunto["a"])
    assert sum(d for _, d in favor) == D("106000")
    await _emitir(mundo, MES_SIGUIENTE)
    assert await _saldo(mundo, conjunto["a"]) == D("494000")  # 600.000 − 106.000 anticipados


async def test_descuento_por_pronto_pago(mundo: Mundo, conjunto: dict[str, uuid.UUID]) -> None:
    admin = await mundo.como(A)
    await comun.guardar_config(
        mundo.db,
        admin,
        ConfigIn(
            metodo=MetodoCuota.COEFICIENTE,
            presupuesto_mensual=D("1000000"),
            dia_vencimiento=10,
            descuento_pct=D("5"),
            dia_limite_descuento=5,
        ),
    )
    await _emitir(mundo, MES_SIGUIENTE)  # emitido hoy, el límite del descuento es el 5 del mes siguiente
    r = await _pagar(mundo, conjunto["a"], "570000")
    assert r.imputacion.descuentos and r.imputacion.descuentos[0][1] == D("30000")
    assert r.saldo_pendiente == 0
    ajuste = (await mundo.db.scalars(select(AjusteCartera))).one()
    assert ajuste.tipo == TipoAjuste.DESCUENTO_PRONTO_PAGO and ajuste.pago_id == r.pago.id

    # Si el pago se anula, el descuento cae con él y la deuda vuelve completa
    await pagos.anular_pago(mundo.db, admin, r.pago.id, "Consignación rechazada por el banco")
    assert await _saldo(mundo, conjunto["a"]) == D("600000")


async def test_referencia_duplicada(mundo: Mundo, conjunto: dict[str, uuid.UUID]) -> None:
    await _emitir(mundo, HOY)
    await _pagar(mundo, conjunto["a"], "100000", medio=MedioPago.TRANSFERENCIA, referencia="tx 123")
    with pytest.raises(ValidacionError, match="TX 123 ya se registró en el recibo"):
        await _pagar(mundo, conjunto["b"], "100000", medio=MedioPago.TRANSFERENCIA, referencia="TX 123")


async def test_permisos(mundo: Mundo, conjunto: dict[str, uuid.UUID]) -> None:
    await _emitir(mundo, HOY)
    contab = await mundo.como(UserRole.CONTABILIDAD)
    r = await pagos.registrar_pago(
        mundo.db,
        contab,
        PagoIn(unidad_id=conjunto["b"], fecha_pago=HOY, valor=D("400000"), medio_pago=MedioPago.EFECTIVO),
    )
    assert r.saldo_pendiente == 0  # contabilidad registra pagos
    with pytest.raises(PermisoDenegado):
        await pagos.anular_pago(mundo.db, contab, r.pago.id, "No debería poder anular")
    aux = await mundo.como(UserRole.AUXILIAR)
    with pytest.raises(PermisoDenegado):
        await facturacion.emitir(mundo.db, aux, EmitirPeriodoIn(anio=HOY.year, mes=MES_SIGUIENTE.month))


# --- Anulaciones y reglas de la base -------------------------------------------------------


async def test_anular_periodo(mundo: Mundo, conjunto: dict[str, uuid.UUID]) -> None:
    await _emitir(mundo, HOY)
    admin = await mundo.como(A)
    periodo = await facturacion._periodo_existente(mundo.db, admin, HOY.year, HOY.month)
    assert periodo is not None
    r = await _pagar(mundo, conjunto["a"], "1000")
    with pytest.raises(ValidacionError, match="Hay pagos"):
        await facturacion.anular_periodo(mundo.db, admin, periodo.id, "Presupuesto mal digitado")
    await pagos.anular_pago(mundo.db, admin, r.pago.id, "Pago de prueba registrado por error")
    await facturacion.anular_periodo(mundo.db, admin, periodo.id, "Presupuesto mal digitado")
    assert await _saldo(mundo, conjunto["a"]) == 0
    await _emitir(mundo, HOY)  # se puede volver a emitir el mes
    assert await _saldo(mundo, conjunto["a"]) == D("600000")


async def test_la_base_impide_editar_y_sobreaplicar(mundo: Mundo, conjunto: dict[str, uuid.UUID]) -> None:
    await _emitir(mundo, HOY)
    await mundo.como(A)
    cargo = (await mundo.db.scalars(select(CargoCartera).where(CargoCartera.unidad_id == conjunto["a"]))).one()
    with pytest.raises(DBAPIError, match="no se editan"):
        async with mundo.db.begin_nested():
            await mundo.db.execute(text("UPDATE cargos_cartera SET valor = 1 WHERE id = :id"), {"id": cargo.id})
    r = await _pagar(mundo, conjunto["a"], "600000")
    with pytest.raises(DBAPIError, match="supera"):
        async with mundo.db.begin_nested():
            await mundo.db.execute(
                text("INSERT INTO aplicaciones_pago (tenant_id, pago_id, cargo_id, valor) VALUES (:t, :p, :c, 1)"),
                {"t": mundo.tenant, "p": r.pago.id, "c": cargo.id},
            )
    for tabla in ("cargos_cartera", "pagos_cartera", "aplicaciones_pago"):
        with pytest.raises(DBAPIError, match="permission denied|No se permite eliminar"):
            async with mundo.db.begin_nested():
                await mundo.db.execute(text(f"DELETE FROM {tabla} WHERE tenant_id = :t"), {"t": mundo.tenant})  # noqa: S608


# --- Cargos manuales y ajustes --------------------------------------------------------------


async def test_cuota_extraordinaria_por_coeficiente_en_cuotas(mundo: Mundo, conjunto: dict[str, uuid.UUID]) -> None:
    admin = await mundo.como(A)
    extra = await comun.concepto(mundo.db, admin, codigo="EXTRAORDINARIA")
    creados = await cargos.crear_cargos(
        mundo.db,
        admin,
        CargoManualIn(
            concepto_id=extra.id,
            descripcion="Impermeabilización de cubiertas",
            todas=True,
            modo="TOTAL_POR_COEFICIENTE",
            valor=D("3000000"),
            numero_cuotas=3,
            primer_vencimiento=HOY + timedelta(days=10),
        ),
    )
    por_unidad: dict[uuid.UUID, list[CargoCartera]] = {}
    for c in creados:
        por_unidad.setdefault(c.unidad_id, []).append(c)
    assert sum(c.valor for c in por_unidad[conjunto["a"]]) == D("1800000")  # 60 %
    cuotas_a = sorted(por_unidad[conjunto["a"]], key=lambda c: c.fecha_vencimiento)
    assert [c.descripcion.endswith(f"(cuota {i} de 3)") for i, c in enumerate(cuotas_a, start=1)] == [True] * 3
    assert cuotas_a[1].fecha_vencimiento.month != cuotas_a[0].fecha_vencimiento.month  # una por mes
    assert conjunto["local"] not in por_unidad  # sin coeficiente
    ordinaria = await comun.concepto(mundo.db, admin, codigo="ADMINISTRACION")
    with pytest.raises(ValidacionError, match="se causan al facturar"):
        await cargos.crear_cargos(
            mundo.db,
            admin,
            CargoManualIn(concepto_id=ordinaria.id, descripcion="x", todas=True, valor=D(1), primer_vencimiento=HOY),
        )


async def test_condonacion(mundo: Mundo, conjunto: dict[str, uuid.UUID]) -> None:
    await _emitir(mundo, MES_PASADO, emision=MES_PASADO)
    await _emitir(mundo, HOY)
    admin = await mundo.como(A)
    interes = (
        await mundo.db.scalars(
            select(CargoCartera)
            .join(ConceptoCartera, ConceptoCartera.id == CargoCartera.concepto_id)
            .where(ConceptoCartera.codigo == "INTERESES_MORA", CargoCartera.unidad_id == conjunto["a"])
        )
    ).one()
    await pagos.ajustar(
        mundo.db,
        admin,
        AjusteIn(
            cargo_id=interes.id, tipo=TipoAjuste.CONDONACION, valor=D("9000"), motivo="Aprobado por el consejo, acta 45"
        ),
    )
    assert await mundo.db.scalar(select(SaldoCargo.saldo).where(SaldoCargo.id == interes.id)) == 0
    with pytest.raises(ValidacionError, match="supera el saldo"):
        await pagos.ajustar(
            mundo.db,
            admin,
            AjusteIn(cargo_id=interes.id, tipo=TipoAjuste.CONDONACION, valor=D("1"), motivo="Otra condonación"),
        )


# --- Paz y salvo y RLS ------------------------------------------------------------------------


async def test_paz_y_salvo_y_vista_del_residente(mundo: Mundo, conjunto: dict[str, uuid.UUID]) -> None:
    await _emitir(mundo, MES_PASADO, emision=MES_PASADO)
    residente = await mundo.como(UserRole.RESIDENTE, "RESIDENTE")
    with pytest.raises(ValidacionError, match="Su unidad tiene un saldo vencido"):
        await paz_y_salvo.emitir(mundo.db, residente, conjunto["a"])
    await _pagar(mundo, conjunto["a"], "600000")
    residente = await mundo.como(UserRole.RESIDENTE, "RESIDENTE")
    p = await paz_y_salvo.emitir(mundo.db, residente, conjunto["a"])
    assert p.consecutivo >= 1 and p.titular_nombre == "Ana Propietaria"
    # El residente solo ve sus cargos y pagos; la unidad ajena no existe para él
    assert {c for c in await mundo.db.scalars(select(CargoCartera.unidad_id))} == {conjunto["a"]}
    assert {c for c in await mundo.db.scalars(select(PagoCartera.unidad_id))} == {conjunto["a"]}
    with pytest.raises(Exception, match="no encontrada"):
        await paz_y_salvo.emitir(mundo.db, residente, conjunto["b"])
    assert (await paz_y_salvo.verificar(mundo.db, residente, p.codigo_verificacion.lower())).id == p.id
    assert (await mundo.db.scalars(select(PagoCartera.estado))).first() == EstadoPagoCartera.APLICADO
