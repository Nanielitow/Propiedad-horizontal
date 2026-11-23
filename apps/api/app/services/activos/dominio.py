"""Reglas puras del módulo de activos y mantenimiento (sin base de datos).

La máquina de estados de las novedades se repite en el trigger
trg_novedades_update (migración 0005); un test verifica que coincidan.
"""

import calendar
import math
import secrets
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from app.models.enums import EstadoNovedad, Periodicidad, UserRole

R = UserRole
N = EstadoNovedad

# --- Permisos (docs/MANTENIMIENTO.md §3) -------------------------------------

PERSONAL = frozenset({R.ADMIN, R.AUXILIAR, R.MANTENIMIENTO, R.CONTABILIDAD})
PUEDE_VER = PERSONAL
PUEDE_CREAR_ACTIVO = frozenset({R.ADMIN})
PUEDE_EDITAR_ACTIVO = frozenset({R.ADMIN, R.AUXILIAR})
PUEDE_DAR_DE_BAJA = frozenset({R.ADMIN})
PUEDE_DOCUMENTAR = frozenset({R.ADMIN, R.AUXILIAR})
PUEDE_SUBIR_FOTOS = frozenset({R.ADMIN, R.AUXILIAR, R.MANTENIMIENTO})
PUEDE_GESTIONAR_CONTRATISTAS = frozenset({R.ADMIN})
PUEDE_CREAR_PLAN = frozenset({R.ADMIN, R.AUXILIAR})
PUEDE_APROBAR_PLAN = frozenset({R.ADMIN})
PUEDE_REPROGRAMAR = frozenset({R.ADMIN, R.AUXILIAR})
PUEDE_REGISTRAR_MANTENIMIENTO = frozenset({R.ADMIN, R.AUXILIAR, R.MANTENIMIENTO})
PUEDE_ANULAR_MANTENIMIENTO = frozenset({R.ADMIN})
PUEDE_REPORTAR_NOVEDAD = frozenset({R.ADMIN, R.AUXILIAR, R.MANTENIMIENTO})
PUEDE_GESTIONAR_NOVEDAD = frozenset({R.ADMIN, R.AUXILIAR, R.MANTENIMIENTO})  # el técnico, solo las asignadas
PUEDE_CERRAR_NOVEDAD = frozenset({R.ADMIN})
PUEDE_GESTIONAR_RECOMENDACION = frozenset({R.ADMIN, R.AUXILIAR, R.MANTENIMIENTO})
PUEDE_DESCARTAR_RECOMENDACION = frozenset({R.ADMIN})
PUEDE_VER_COSTOS = frozenset({R.ADMIN, R.CONTABILIDAD})


def nuevo_qr_token() -> str:
    """32 caracteres aleatorios seguros (URL-safe). No contiene datos del activo."""
    return secrets.token_urlsafe(24)


# --- Periodicidad --------------------------------------------------------------

_DIAS = {Periodicidad.SEMANAL: 7, Periodicidad.QUINCENAL: 15}
_MESES = {
    Periodicidad.MENSUAL: 1,
    Periodicidad.BIMESTRAL: 2,
    Periodicidad.TRIMESTRAL: 3,
    Periodicidad.SEMESTRAL: 6,
    Periodicidad.ANUAL: 12,
}


def sumar_meses(d: date, meses: int) -> date:
    """31 de enero + 1 mes = 28 (o 29) de febrero: se ajusta al último día del mes."""
    total = d.month - 1 + meses
    anio, mes = d.year + total // 12, total % 12 + 1
    return date(anio, mes, min(d.day, calendar.monthrange(anio, mes)[1]))


def ocurrencia(inicio: date, periodicidad: Periodicidad, k: int) -> date:
    """La k-ésima fecha desde el inicio. Se calcula SIEMPRE desde el inicio (no
    encadenando), así un 31 que cae en febrero no arrastra el 28 a todos los meses."""
    if periodicidad in _DIAS:
        return inicio + timedelta(days=_DIAS[periodicidad] * k)
    if periodicidad in _MESES:
        return sumar_meses(inicio, _MESES[periodicidad] * k)
    raise ValueError("Los planes por horas de uso no tienen fechas fijas")


def fechas_programables(inicio: date, periodicidad: Periodicidad, desde: date, hasta: date) -> list[date]:
    """Ocurrencias de un plan de calendario fijo entre `desde` y `hasta` (incluidos)."""
    fechas: list[date] = []
    k = 0
    while (f := ocurrencia(inicio, periodicidad, k)) <= hasta:
        if f >= desde:
            fechas.append(f)
        k += 1
    return fechas


def siguiente_fecha(base: date, periodicidad: Periodicidad) -> date:
    return ocurrencia(base, periodicidad, 1)


# --- Semáforo ------------------------------------------------------------------

Color = Literal["VERDE", "AMARILLO", "ROJO"]
UMBRAL_DIAS = 15


def semaforo(fecha_programada: date, hoy: date, umbral: int = UMBRAL_DIAS) -> tuple[Color, int]:
    """Verde: faltan más de `umbral` días. Amarillo: entre 0 (vence hoy) y `umbral`.
    Rojo: la fecha ya pasó sin ejecución. Igual que la vista v_semaforo_actividades."""
    dias = (fecha_programada - hoy).days
    if dias < 0:
        return "ROJO", dias
    if dias <= umbral:
        return "AMARILLO", dias
    return "VERDE", dias


PEOR: dict[Color, int] = {"VERDE": 0, "AMARILLO": 1, "ROJO": 2}


def peor_color(colores: list[Color]) -> Color | None:
    """El semáforo de un activo es el peor de sus actividades pendientes."""
    return max(colores, key=PEOR.__getitem__) if colores else None


@dataclass(frozen=True)
class EstadoPorHoras:
    horas_restantes: Decimal
    color: Color
    fecha_estimada: date | None  # None si no hay uso medido


def estado_por_horas(
    intervalo: int, horas_desde_ultimo: Decimal, uso_diario: Decimal | None, hoy: date
) -> EstadoPorHoras:
    """Plan por horas de uso: rojo si se pasó del intervalo, amarillo si queda menos del 10 %."""
    restantes = Decimal(intervalo) - horas_desde_ultimo
    color: Color = "ROJO" if restantes <= 0 else "AMARILLO" if restantes < Decimal(intervalo) / 10 else "VERDE"
    fecha = None
    if uso_diario and uso_diario > 0:
        fecha = hoy + timedelta(days=max(0, math.ceil(restantes / uso_diario)))
    return EstadoPorHoras(restantes, color, fecha)


def vida_util_consumida(fecha_instalacion: date | None, vida_util_anios: int | None, hoy: date) -> Decimal | None:
    if not fecha_instalacion or not vida_util_anios:
        return None
    dias = (hoy - fecha_instalacion).days
    return (Decimal(dias) / Decimal(vida_util_anios * 365) * 100).quantize(Decimal("0.1"))


# --- Novedades -------------------------------------------------------------------

TRANSICIONES_NOVEDAD: dict[EstadoNovedad, frozenset[EstadoNovedad]] = {
    N.REPORTADA: frozenset({N.EN_GESTION, N.DESCARTADA}),
    N.EN_GESTION: frozenset({N.PENDIENTE_COTIZACION, N.PROGRAMADA, N.EN_EJECUCION, N.DESCARTADA}),
    N.PENDIENTE_COTIZACION: frozenset({N.PROGRAMADA, N.DESCARTADA}),
    N.PROGRAMADA: frozenset({N.EN_EJECUCION}),
    N.EN_EJECUCION: frozenset({N.CERRADA}),
    N.CERRADA: frozenset(),
    N.DESCARTADA: frozenset(),
}
NOVEDAD_ABIERTA = frozenset(e for e in N if e not in (N.CERRADA, N.DESCARTADA))
