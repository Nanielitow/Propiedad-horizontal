"""Reglas puras de las asambleas (Ley 675 de 2001). docs/ASAMBLEAS.md.

- Quórum (art. 45): en primera convocatoria, más de la mitad de los coeficientes del conjunto.
  En segunda convocatoria (art. 41), cualquier número plural de propietarios.
- Mayoría simple (art. 45): la mitad más uno de los coeficientes representados en la sesión.
- Mayoría calificada (art. 46): 70 % de los coeficientes de TODO el conjunto; no se rebaja en
  segunda convocatoria.
- Elección: gana la opción con más coeficiente; un empate no elige a nadie.
- Convocatoria con 15 días calendario de anticipación (art. 39).

Por convención, en los puntos de mayoría simple o calificada la PRIMERA opción es «a favor».
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.models.enums import ConvocatoriaAsamblea, MayoriaPunto, UserRole

R = UserRole
CERO = Decimal(0)
OPCIONES_DEFECTO = ["Sí", "No", "Abstención"]
DIAS_CONVOCATORIA = 15
UMBRAL_CALIFICADA = Decimal("0.70")

PUEDE_GESTIONAR = frozenset({R.ADMIN})
PUEDE_REGISTRAR_ASISTENCIA = frozenset({R.ADMIN, R.AUXILIAR})  # en sala: asistencia y votos a mano alzada
PUEDE_VER = frozenset({R.ADMIN, R.AUXILIAR, R.CONSEJO, R.CONTABILIDAD, R.RESIDENTE})


# --- Quórum ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Quorum:
    presente: Decimal  # coeficiente presente
    total: Decimal  # coeficiente del padrón
    unidades_presentes: int
    unidades_total: int
    convocatoria: ConvocatoriaAsamblea

    @property
    def porcentaje(self) -> Decimal:
        return (self.presente / self.total * 100).quantize(Decimal("0.01")) if self.total else CERO

    @property
    def hay_quorum(self) -> bool:
        if self.convocatoria == ConvocatoriaAsamblea.SEGUNDA:
            return self.unidades_presentes >= 2  # número plural (art. 41)
        return self.total > 0 and self.presente * 2 > self.total  # más de la mitad (art. 45)

    @property
    def falta(self) -> Decimal:
        """Coeficiente que falta para el quórum de primera convocatoria (0 si ya lo hay)."""
        if self.convocatoria == ConvocatoriaAsamblea.SEGUNDA or self.hay_quorum:
            return CERO
        return (self.total / 2 - self.presente + Decimal("0.0001")).quantize(Decimal("0.0001"))

    @property
    def mensaje(self) -> str:
        pct = f"{self.porcentaje:.2f}".replace(".", ",")
        if self.convocatoria == ConvocatoriaAsamblea.SEGUNDA:
            return f"Segunda convocatoria: {self.unidades_presentes} unidades presentes ({pct} % de los coeficientes)"
        if self.hay_quorum:
            return f"Hay quórum: {pct} % de los coeficientes presentes"
        return f"Sin quórum: {pct} % presente; se necesita más del 50 %"


# --- Resultados -----------------------------------------------------------------------------


@dataclass
class Resultado:
    por_opcion: dict[str, Decimal] = field(default_factory=dict)
    unidades_por_opcion: dict[str, int] = field(default_factory=dict)
    votantes: Decimal = CERO  # coeficiente que votó
    presente: Decimal = CERO
    total: Decimal = CERO
    aprobado: bool | None = None  # None en elecciones
    ganador: str | None = None
    umbral: Decimal = CERO  # coeficiente necesario para aprobar
    explicacion: str = ""

    def a_json(self) -> dict[str, object]:
        return {
            "por_opcion": {k: str(v) for k, v in self.por_opcion.items()},
            "unidades_por_opcion": self.unidades_por_opcion,
            "votantes": str(self.votantes),
            "presente": str(self.presente),
            "total": str(self.total),
            "aprobado": self.aprobado,
            "ganador": self.ganador,
            "umbral": str(self.umbral),
            "explicacion": self.explicacion,
        }


def _pct(v: Decimal, base: Decimal) -> str:
    return f"{(v / base * 100):.2f}".replace(".", ",") if base else "0,00"


def resultado(
    mayoria: MayoriaPunto,
    opciones: list[str],
    votos: list[tuple[str, Decimal]],
    *,
    presente: Decimal,
    total: Decimal,
) -> Resultado:
    r = Resultado(presente=presente, total=total)
    r.por_opcion = dict.fromkeys(opciones, CERO)
    r.unidades_por_opcion = dict.fromkeys(opciones, 0)
    for opcion, coef in votos:
        r.por_opcion[opcion] = r.por_opcion.get(opcion, CERO) + coef
        r.unidades_por_opcion[opcion] = r.unidades_por_opcion.get(opcion, 0) + 1
        r.votantes += coef
    if mayoria == MayoriaPunto.ELECCION:
        orden = sorted(r.por_opcion.items(), key=lambda kv: kv[1], reverse=True)
        if orden and orden[0][1] > 0 and (len(orden) == 1 or orden[0][1] > orden[1][1]):
            r.ganador = orden[0][0]
            r.explicacion = f"Elegido: {r.ganador} con {_pct(orden[0][1], presente)} % de los coeficientes presentes"
        else:
            r.explicacion = "Empate o sin votos: no hay elegido"
        return r

    a_favor = r.por_opcion.get(opciones[0], CERO)
    if mayoria == MayoriaPunto.SIMPLE:
        r.umbral = presente / 2  # se necesita MÁS que esto
        r.aprobado = a_favor > r.umbral
        r.explicacion = (
            f"{'Aprobado' if r.aprobado else 'No aprobado'}: {_pct(a_favor, presente)} % de los coeficientes presentes a favor "
            "(mayoría simple: más del 50 % de los presentes)"
        )
    else:
        r.umbral = (total * UMBRAL_CALIFICADA).quantize(Decimal("0.0001"))
        r.aprobado = a_favor >= r.umbral
        r.explicacion = (
            f"{'Aprobado' if r.aprobado else 'No aprobado'}: {_pct(a_favor, total)} % de los coeficientes del conjunto a favor "
            "(mayoría calificada: 70 % del total, art. 46 de la Ley 675)"
        )
    return r


# --- Convocatoria y poderes --------------------------------------------------------------


def aviso_convocatoria(fecha_asamblea: date, fecha_convocatoria: date) -> str | None:
    dias = (fecha_asamblea - fecha_convocatoria).days
    if dias < DIAS_CONVOCATORIA:
        return (
            f"La convocatoria se hace con {dias} día(s) de anticipación; la Ley 675 (art. 39) pide al menos "
            f"{DIAS_CONVOCATORIA} días calendario para la asamblea ordinaria"
        )
    return None


def normalizar_opciones(opciones: list[str] | None, mayoria: MayoriaPunto) -> list[str]:
    limpias = []
    for o in opciones or []:
        o = " ".join(o.split())
        if o and o.lower() not in {x.lower() for x in limpias}:
            limpias.append(o)
    if mayoria != MayoriaPunto.ELECCION and not limpias:
        return list(OPCIONES_DEFECTO)
    return limpias
