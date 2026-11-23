"""Reglas de dominio puras del módulo de recaudos (sin base de datos).

La máquina de estados y los permisos se repiten en la base de datos (triggers y
RLS de la migración 0003) a propósito: aquí dan errores claros y tempranos a
la API; allá garantizan que ni un error de código pueda saltárselos.
Los tests verifican que ambas definiciones coincidan.
"""

import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from zoneinfo import ZoneInfo

from app.models.enums import EstadoRecaudo, MedioPago, TipoCobro, UserRole

TZ = ZoneInfo("America/Bogota")
E = EstadoRecaudo


# --- Errores de dominio (la API los traduce a 400/403/404/409) -----------------


class RecaudoError(Exception):
    """Error de negocio con mensaje apto para mostrar al usuario."""


class ValidacionError(RecaudoError):
    pass


class PermisoDenegado(RecaudoError):
    pass


class NoEncontrado(RecaudoError):
    pass


class TransicionInvalida(RecaudoError):
    pass


# --- Quién actúa ---------------------------------------------------------------


class Actor(Protocol):
    """Lo cumple TenantContext de la API; el servicio no depende de FastAPI."""

    @property
    def tenant_id(self) -> uuid.UUID: ...
    @property
    def user_id(self) -> uuid.UUID: ...
    @property
    def role(self) -> UserRole: ...


@dataclass(frozen=True)
class ActorSimple:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    role: UserRole


# --- Permisos (matriz de docs/RECAUDOS.md §2) -------------------------------

R = UserRole
PUEDE_REGISTRAR = frozenset({R.ADMIN, R.AUXILIAR})
PUEDE_EDITAR = frozenset({R.ADMIN, R.AUXILIAR})
PUEDE_ANULAR = frozenset({R.ADMIN})
PUEDE_VERIFICAR = frozenset({R.ADMIN, R.CONTABILIDAD})
PUEDE_VER_TODO = frozenset({R.ADMIN, R.CONTABILIDAD})
PUEDE_VER_AUDITORIA = frozenset({R.ADMIN, R.CONTABILIDAD})
PUEDE_GESTIONAR_CATALOGOS = frozenset({R.ADMIN})
PUEDE_CERRAR_CAJA = frozenset({R.ADMIN, R.AUXILIAR})
PUEDE_ENTREGAR = frozenset({R.ADMIN, R.AUXILIAR})
PUEDE_RECIBIR_ENTREGA = frozenset({R.ADMIN})  # la administración/tesorería recibe el efectivo
PUEDE_CONSIGNAR = frozenset({R.ADMIN, R.AUXILIAR})
PUEDE_APROBAR_CONSIGNACION = frozenset({R.ADMIN, R.CONTABILIDAD})
PUEDE_VER_ALERTAS = frozenset({R.ADMIN, R.CONTABILIDAD})
PUEDE_ATENDER_ALERTAS = frozenset({R.ADMIN})


def exigir(actor: Actor, permitidos: frozenset[UserRole], accion: str) -> None:
    if actor.role not in permitidos:
        raise PermisoDenegado(f"Su rol ({actor.role.value}) no permite {accion}")


# --- Máquina de estados -------------------------------------------------------

TRANSICIONES: dict[EstadoRecaudo, frozenset[EstadoRecaudo]] = {
    E.RECAUDADO_EN_CAJA: frozenset({E.ENTREGADO_ADMINISTRACION, E.CONSIGNADO, E.ANULADO}),
    E.ENTREGADO_ADMINISTRACION: frozenset({E.CONSIGNADO, E.ANULADO}),
    E.PENDIENTE_VERIFICACION: frozenset({E.VERIFICADO, E.ANULADO}),
    E.CONSIGNADO: frozenset({E.VERIFICADO, E.ANULADO}),
    E.VERIFICADO: frozenset({E.ANULADO}),
    E.ANULADO: frozenset(),
}

# Anular algo cuyo dinero ya está en el banco merece una alerta de auditoría
ANULACION_REQUIERE_ALERTA = frozenset({E.CONSIGNADO, E.VERIFICADO})


def estado_inicial(medio: MedioPago) -> EstadoRecaudo:
    return E.RECAUDADO_EN_CAJA if medio == MedioPago.EFECTIVO else E.PENDIENTE_VERIFICACION


def validar_transicion(actual: EstadoRecaudo, nuevo: EstadoRecaudo) -> None:
    if nuevo not in TRANSICIONES[actual]:
        raise TransicionInvalida(f"No se puede pasar de {actual.value} a {nuevo.value}")


# --- Tarifas ------------------------------------------------------------------


@dataclass(frozen=True)
class CalculoParqueadero:
    minutos: int
    fracciones: int
    tarifa_sugerida: Decimal


def calcular_parqueadero(
    ingreso: datetime, salida: datetime, tarifa_por_fraccion: Decimal, fraccion_minutos: int
) -> CalculoParqueadero:
    """Cobra por fracción iniciada: con fracción de 60 min, 61 minutos son 2 horas.

    Los minutos se redondean hacia arriba igual que la columna generada
    `recaudo_parqueadero.minutos_totales`, para que ambos coincidan.
    """
    if salida <= ingreso:
        raise ValidacionError("La hora de salida debe ser posterior a la de ingreso")
    if fraccion_minutos <= 0:
        raise ValidacionError("El concepto de parqueadero no tiene fracción de cobro configurada")
    minutos = math.ceil((salida - ingreso).total_seconds() / 60)
    fracciones = max(1, math.ceil(minutos / fraccion_minutos))
    return CalculoParqueadero(minutos, fracciones, (tarifa_por_fraccion * fracciones).quantize(Decimal("0.01")))


def valor_por_defecto(tipo: TipoCobro, tarifa_base: Decimal | None) -> Decimal | None:
    """Valor sugerido cuando el usuario no lo escribe (solo para cobros fijos)."""
    return tarifa_base if tipo == TipoCobro.FIJO and tarifa_base else None


def es_mismo_dia_bogota(a: datetime, b: datetime) -> bool:
    return a.astimezone(TZ).date() == b.astimezone(TZ).date()


def pesos(valor: Decimal) -> str:
    """Formato colombiano para mensajes: Decimal('1234567.5') -> '$1.234.568'."""
    signo = "-" if valor < 0 else ""
    return f"{signo}${abs(valor):,.0f}".replace(",", ".")


_SOPORTE = re.compile(r"^tenants/(?P<tenant>[0-9a-f-]{36})/recaudos/soportes/[0-9a-f-]{36}\.(pdf|jpg|png|webp)$")
SOPORTE_TIPOS = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def validar_soporte(actor: Actor, key: str | None) -> None:
    """Un soporte solo puede referenciar un archivo subido en la carpeta de SU copropiedad."""
    if key is None:
        return
    m = _SOPORTE.fullmatch(key)
    if m is None or m.group("tenant") != str(actor.tenant_id):
        raise ValidacionError("El soporte adjunto no es válido: súbalo de nuevo")
