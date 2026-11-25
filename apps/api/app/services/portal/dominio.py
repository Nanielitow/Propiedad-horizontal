"""Reglas puras del portal del residente (sin base de datos). docs/PORTAL.md.

- Plazo de respuesta de una PQRS: 15 días hábiles (como el derecho de petición de la
  Ley 1755 de 2015, que las copropiedades suelen adoptar), sin sábados, domingos ni
  festivos colombianos (Ley 51 de 1983, «Ley Emiliani», y los que dependen de la Pascua).
- Reglas de reserva de una zona social: horario, anticipación, cupo mensual por unidad.
- La máquina de estados de la PQRS se repite en el trigger trg_pqrs_update (0009).
"""

from dataclasses import dataclass
from datetime import date, time, timedelta
from functools import lru_cache

from app.models.enums import EstadoPqrs, UserRole

R = UserRole
E = EstadoPqrs

# --- Permisos ----------------------------------------------------------------------------

PUEDE_GESTIONAR_PQRS = frozenset({R.ADMIN, R.AUXILIAR})  # bandeja completa: asignar, responder, cerrar
PUEDE_VER_PQRS = frozenset({R.ADMIN, R.AUXILIAR, R.CONSEJO, R.CONTABILIDAD, R.MANTENIMIENTO})  # la RLS acota
PUEDE_RADICAR_A_NOMBRE = frozenset({R.ADMIN, R.AUXILIAR})  # PQRS presencial, por correo o teléfono
PUEDE_PUBLICAR_CIRCULAR = frozenset({R.ADMIN})
PUEDE_REDACTAR_CIRCULAR = frozenset({R.ADMIN, R.AUXILIAR})
PUEDE_VER_LECTURAS = frozenset({R.ADMIN, R.AUXILIAR, R.CONSEJO})
PUEDE_DECIDIR_RESERVA = frozenset({R.ADMIN, R.AUXILIAR})
PUEDE_CONFIGURAR_ZONAS = frozenset({R.ADMIN})

PLAZO_DIAS_HABILES = 15

TRANSICIONES_PQRS: dict[EstadoPqrs, frozenset[EstadoPqrs]] = {
    E.RADICADA: frozenset({E.EN_TRAMITE, E.RESPONDIDA, E.DESISTIDA}),
    E.EN_TRAMITE: frozenset({E.RESPONDIDA, E.DESISTIDA}),
    E.RESPONDIDA: frozenset({E.EN_TRAMITE, E.CERRADA}),
    E.CERRADA: frozenset(),
    E.DESISTIDA: frozenset(),
}
ABIERTAS = frozenset({E.RADICADA, E.EN_TRAMITE})


def puede_pasar(de: EstadoPqrs, a: EstadoPqrs) -> bool:
    return a in TRANSICIONES_PQRS[de]


# --- Festivos y días hábiles ----------------------------------------------------------------


def _pascua(anio: int) -> date:
    """Domingo de Pascua (algoritmo de Meeus/Butcher para el calendario gregoriano)."""
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    mes = (h + m - 7 * n + 114) // 31
    dia = (h + m - 7 * n + 114) % 31 + 1
    return date(anio, mes, dia)


def _lunes_siguiente(d: date) -> date:
    """Ley Emiliani: el festivo se traslada al lunes siguiente (si no cae en lunes)."""
    return d + timedelta(days=(7 - d.weekday()) % 7)


@lru_cache(maxsize=32)
def festivos(anio: int) -> frozenset[date]:
    fijos = [
        date(anio, 1, 1),
        date(anio, 5, 1),
        date(anio, 7, 20),
        date(anio, 8, 7),
        date(anio, 12, 8),
        date(anio, 12, 25),
    ]
    emiliani = [
        date(anio, 1, 6),  # Reyes Magos
        date(anio, 3, 19),  # San José
        date(anio, 6, 29),  # San Pedro y San Pablo
        date(anio, 8, 15),  # Asunción
        date(anio, 10, 12),  # Día de la Raza
        date(anio, 11, 1),  # Todos los Santos
        date(anio, 11, 11),  # Independencia de Cartagena
    ]
    p = _pascua(anio)
    pascuales = [p - timedelta(days=3), p - timedelta(days=2)]  # Jueves y Viernes Santo
    pascuales_lunes = [
        p + timedelta(days=43),
        p + timedelta(days=64),
        p + timedelta(days=71),
    ]  # Ascensión, Corpus, Sagrado Corazón
    return frozenset(fijos + [_lunes_siguiente(d) for d in emiliani] + pascuales + pascuales_lunes)


def es_habil(d: date) -> bool:
    return d.weekday() < 5 and d not in festivos(d.year)


def sumar_dias_habiles(desde: date, dias: int) -> date:
    """El día de radicación no cuenta: 15 días hábiles después."""
    d, contados = desde, 0
    while contados < dias:
        d += timedelta(days=1)
        if es_habil(d):
            contados += 1
    return d


def dias_habiles_entre(desde: date, hasta: date) -> int:
    """Días hábiles que faltan (positivo) o de atraso (negativo) de `desde` a `hasta`."""
    if hasta == desde:
        return 0
    signo = 1 if hasta > desde else -1
    a, b = sorted((desde, hasta))
    n = sum(1 for k in range(1, (b - a).days + 1) if es_habil(a + timedelta(days=k)))
    return signo * n


# --- Reservas -------------------------------------------------------------------------------


@dataclass(frozen=True)
class ReglasZona:
    hora_apertura: time
    hora_cierre: time
    anticipacion_min_dias: int
    anticipacion_max_dias: int
    max_reservas_mes_unidad: int
    capacidad: int | None


def validar_reserva(
    r: ReglasZona,
    *,
    hoy: date,
    fecha: date,
    hora_inicio: time | None,
    hora_fin: time | None,
    asistentes: int | None,
    reservas_del_mes: int,
) -> list[str]:
    """Errores (en español, para mostrar) si la solicitud no cumple las reglas de la zona."""
    errores: list[str] = []
    dias = (fecha - hoy).days
    if dias < r.anticipacion_min_dias:
        errores.append(
            "La fecha ya pasó"
            if dias < 0
            else f"Debe reservar con al menos {r.anticipacion_min_dias} día(s) de anticipación"
        )
    if dias > r.anticipacion_max_dias:
        errores.append(f"Solo se puede reservar hasta {r.anticipacion_max_dias} días antes")
    if hora_inicio is None or hora_fin is None:
        errores.append("Indique la hora de inicio y de fin")
    else:
        if hora_fin <= hora_inicio:
            errores.append("La hora de fin debe ser posterior a la de inicio")
        if hora_inicio < r.hora_apertura or hora_fin > r.hora_cierre:
            errores.append(f"La zona funciona de {r.hora_apertura:%H:%M} a {r.hora_cierre:%H:%M}")
    if asistentes is not None and r.capacidad is not None and asistentes > r.capacidad:
        errores.append(f"La capacidad máxima es de {r.capacidad} personas")
    if reservas_del_mes >= r.max_reservas_mes_unidad:
        errores.append(
            f"Su unidad ya tiene {reservas_del_mes} reserva(s) este mes (máximo {r.max_reservas_mes_unidad})"
        )
    return errores
