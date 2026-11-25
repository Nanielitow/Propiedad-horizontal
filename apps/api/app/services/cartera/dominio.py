"""Reglas puras de la cartera (sin base de datos). docs/CARTERA.md.

- Cuota ordinaria: presupuesto mensual × coeficiente / 100, o tarifa por tipo de unidad,
  redondeada al múltiplo configurado (por defecto $100).
- Intereses de mora: capital vencido que genera interés × tasa mensual. Los intereses no
  generan intereses (anatocismo, art. 2235 del Código Civil).
- Imputación de pagos (art. 1653 del Código Civil): primero intereses, después capital,
  de lo más antiguo a lo más reciente.
- Descuento por pronto pago: solo si, con ese pago, la unidad queda al día en todo lo
  anterior y alcanza para la cuota con descuento, antes de la fecha límite.
"""

import calendar
import secrets
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.models.enums import UserRole

R = UserRole
CERO = Decimal(0)

# --- Permisos (docs/CARTERA.md §4) -------------------------------------------------

PUEDE_VER = frozenset({R.ADMIN, R.CONTABILIDAD, R.AUXILIAR, R.CONSEJO})
PUEDE_CONFIGURAR = frozenset({R.ADMIN})
PUEDE_FACTURAR = frozenset({R.ADMIN})
PUEDE_CARGAR = frozenset({R.ADMIN})  # cuotas extraordinarias, multas
PUEDE_REGISTRAR_PAGO = frozenset({R.ADMIN, R.CONTABILIDAD})
PUEDE_ANULAR = frozenset({R.ADMIN})
PUEDE_AJUSTAR = frozenset({R.ADMIN})  # condonaciones y correcciones
PUEDE_PAZ_Y_SALVO = frozenset({R.ADMIN, R.CONTABILIDAD, R.AUXILIAR, R.RESIDENTE})  # el residente: el suyo
PUEDE_VER_AUDITORIA = frozenset({R.ADMIN, R.CONTABILIDAD})


# --- Dinero ----------------------------------------------------------------------------


def redondear(valor: Decimal, multiplo: int = 1) -> Decimal:
    """Al múltiplo más cercano (mitad hacia arriba): 245_349 -> 245_300 con múltiplo 100."""
    m = Decimal(multiplo)
    return ((valor / m).quantize(Decimal(1), rounding=ROUND_HALF_UP) * m).quantize(Decimal("0.01"))


def cuota_por_coeficiente(presupuesto_mensual: Decimal, coeficiente: Decimal, multiplo: int) -> Decimal:
    return redondear(presupuesto_mensual * coeficiente / 100, multiplo)


def cuota_por_tipo(tarifas: dict[str, object], tipo: str, multiplo: int) -> Decimal | None:
    valor = tarifas.get(tipo)
    if valor in (None, "", 0, "0"):
        return None
    return redondear(Decimal(str(valor)), multiplo)


def interes_mora(capital_vencido: Decimal, tasa_mensual_pct: Decimal) -> Decimal:
    """Interés de un mes sobre el capital vencido, redondeado al peso."""
    if capital_vencido <= 0 or tasa_mensual_pct <= 0:
        return CERO
    return redondear(capital_vencido * tasa_mensual_pct / 100, 1)


def descuento(valor: Decimal, pct: Decimal) -> Decimal:
    return redondear(valor * pct / 100, 1)


# --- Fechas del periodo -------------------------------------------------------------------


MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]  # fmt: skip


def nombre_periodo(anio: int, mes: int) -> str:
    return f"{MESES[mes - 1]} de {anio}"


@dataclass(frozen=True)
class FechasPeriodo:
    vencimiento: date
    limite_descuento: date | None


def fechas_periodo(anio: int, mes: int, dia_vencimiento: int, dia_limite_descuento: int | None) -> FechasPeriodo:
    ultimo = calendar.monthrange(anio, mes)[1]
    venc = date(anio, mes, min(dia_vencimiento, ultimo))
    limite = None
    if dia_limite_descuento:
        limite = min(date(anio, mes, min(dia_limite_descuento, ultimo)), venc)
    return FechasPeriodo(venc, limite)


def fin_de_mes(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


# --- Imputación de pagos -------------------------------------------------------------------


@dataclass(frozen=True)
class CargoPendiente:
    id: uuid.UUID
    es_interes: bool
    fecha_vencimiento: date
    fecha_causacion: date
    valor: Decimal
    saldo: Decimal
    descuento_pct: Decimal | None = None
    fecha_limite_descuento: date | None = None


@dataclass
class Imputacion:
    aplicaciones: list[tuple[uuid.UUID, Decimal]] = field(default_factory=list)
    descuentos: list[tuple[uuid.UUID, Decimal]] = field(default_factory=list)
    sobrante: Decimal = CERO  # queda como saldo a favor

    @property
    def aplicado(self) -> Decimal:
        return sum((v for _, v in self.aplicaciones), CERO)


def orden_imputacion(cargos: Iterable[CargoPendiente]) -> list[CargoPendiente]:
    """Intereses primero; dentro de cada grupo, lo que venció antes."""
    return sorted(
        (c for c in cargos if c.saldo > 0),
        key=lambda c: (not c.es_interes, c.fecha_vencimiento, c.fecha_causacion, str(c.id)),
    )


def imputar(monto: Decimal, cargos: Iterable[CargoPendiente], fecha_pago: date) -> Imputacion:
    r = Imputacion()
    disponible = monto
    al_dia = True  # ¿todo lo anterior en el orden quedó pagado?
    for c in orden_imputacion(cargos):
        if disponible <= 0:
            break
        desc = CERO
        if (
            al_dia
            and c.descuento_pct
            and c.fecha_limite_descuento
            and fecha_pago <= c.fecha_limite_descuento
            and c.saldo == c.valor  # el descuento se da sobre la cuota completa, una sola vez
        ):
            posible = descuento(c.valor, c.descuento_pct)
            if disponible >= c.saldo - posible:
                desc = posible
        a_pagar = c.saldo - desc
        aplicado = min(disponible, a_pagar)
        if aplicado > 0:
            r.aplicaciones.append((c.id, aplicado))
        if desc > 0:
            r.descuentos.append((c.id, desc))
        disponible -= aplicado
        if aplicado < a_pagar:
            al_dia = False
    r.sobrante = disponible
    return r


# --- Antigüedad de la cartera --------------------------------------------------------------

RANGOS = ("corriente", "1_30", "31_60", "61_90", "mas_90")


def dias_mora(fecha_vencimiento: date, corte: date) -> int:
    return max(0, (corte - fecha_vencimiento).days)


def rango(dias: int) -> str:
    if dias <= 0:
        return "corriente"
    if dias <= 30:
        return "1_30"
    if dias <= 60:
        return "31_60"
    if dias <= 90:
        return "61_90"
    return "mas_90"


def edades(saldos: Iterable[tuple[date, Decimal]], corte: date) -> dict[str, Decimal]:
    """(fecha de vencimiento, saldo) -> saldo por rango de días de mora."""
    r = dict.fromkeys(RANGOS, CERO)
    for venc, saldo in saldos:
        if saldo > 0:
            r[rango(dias_mora(venc, corte))] += saldo
    return r


# --- Paz y salvo ---------------------------------------------------------------------------

_ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I: se dicta por teléfono sin errores


def codigo_verificacion() -> str:
    """'K7QX-M3PA-9TZD': 12 caracteres aleatorios, ~60 bits."""
    c = "".join(secrets.choice(_ALFABETO) for _ in range(12))
    return f"{c[:4]}-{c[4:8]}-{c[8:]}"
