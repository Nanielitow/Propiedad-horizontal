"""Reglas puras del módulo de unidades (sin base de datos). docs/UNIDADES.md.

Las usan los servicios, el importador de Excel y los esquemas de entrada, para
que una misma cédula o un mismo coeficiente se interpreten igual en todas partes.
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.models.enums import OcupacionUnidad, RelacionUnidad, TipoDocumentoIdentidad, UserRole

R = UserRole

# --- Permisos (docs/UNIDADES.md §3) ---------------------------------------------

PUEDE_VER_UNIDADES = frozenset({R.ADMIN, R.AUXILIAR, R.CONTABILIDAD, R.CONSEJO, R.MANTENIMIENTO})
PUEDE_VER_DATOS_PREDIALES = frozenset({R.ADMIN, R.CONTABILIDAD, R.CONSEJO})  # coeficiente, área, matrícula
PUEDE_VER_DIRECTORIO = frozenset({R.ADMIN, R.AUXILIAR, R.CONTABILIDAD})
PUEDE_VER_DATOS_SENSIBLES = frozenset({R.ADMIN, R.CONTABILIDAD})  # documento, correo, notas
PUEDE_VER_VEHICULOS = frozenset({R.ADMIN, R.AUXILIAR})
PUEDE_GESTIONAR = frozenset({R.ADMIN})
PUEDE_EXPORTAR = frozenset({R.ADMIN, R.CONTABILIDAD, R.CONSEJO})
PUEDE_VER_AUDITORIA = frozenset({R.ADMIN, R.CONTABILIDAD})


# --- Normalización -------------------------------------------------------------

_DOC_LIMPIAR = re.compile(r"[\s.,]")
_DOC_VALIDO = re.compile(r"^[A-Z0-9-]{3,20}$")
_PLACA_LIMPIAR = re.compile(r"[\s\-.]")
_PLACA_VALIDA = re.compile(r"^[A-Z0-9]{3,7}$")
_TELEFONO_LIMPIAR = re.compile(r"[^\d+]")


def normalizar_documento(valor: str) -> str:
    """'1.020.304.050' / ' 1020 304050 ' -> '1020304050'. NIT conserva el guion: '900.123.456-7' -> '900123456-7'."""
    doc = _DOC_LIMPIAR.sub("", valor).upper()
    if not _DOC_VALIDO.fullmatch(doc):
        raise ValueError(f"El número de documento «{valor}» no es válido")
    return doc


def normalizar_placa(valor: str) -> str:
    """'abc-123' -> 'ABC123'. Admite marcaciones cortas de bicicleta (3 caracteres)."""
    placa = _PLACA_LIMPIAR.sub("", valor).upper()
    if not _PLACA_VALIDA.fullmatch(placa):
        raise ValueError(f"La placa «{valor}» no es válida")
    return placa


def normalizar_telefono(valor: str) -> str:
    """'(+57) 300 123-4567' -> '+573001234567'. Rechaza lo que no tenga entre 7 y 15 dígitos."""
    tel = _TELEFONO_LIMPIAR.sub("", valor)
    digitos = tel.lstrip("+")
    if not digitos.isdigit() or not 7 <= len(digitos) <= 15 or "+" in digitos:
        raise ValueError(f"El teléfono «{valor}» no es válido")
    return tel


def normalizar_nombre(valor: str) -> str:
    """Quita espacios repetidos. 'JUAN  pérez' -> 'Juan Pérez' solo si viene todo en mayúsculas o minúsculas
    (respeta 'María del Pilar McAllister' tal como lo escribió la persona)."""
    nombre = " ".join(valor.split())
    if not nombre:
        raise ValueError("El nombre es obligatorio")
    if nombre.isupper() or nombre.islower():
        conectores = {"de", "del", "la", "las", "los", "y"}
        palabras = nombre.lower().split(" ")
        nombre = " ".join(p if (i and p in conectores) else p.capitalize() for i, p in enumerate(palabras))
    return nombre


def normalizar_torre(valor: str | None) -> str:
    """'torre 2' / 'T2' / ' 2 ' -> '2'. Vacío si el conjunto no tiene torres. 'Bloque A' -> 'A'."""
    if valor is None:
        return ""
    t = " ".join(str(valor).split()).upper()
    # La palabra debe ir seguida de un separador o un dígito: "Interior 4" sí, "Internacional" no
    t = re.sub(r"^(TORRE|BLOQUE|INTERIOR|INT\.?)(?:\s*[-.]\s*|\s+|(?=\d))(?=[A-Z0-9])", "", t)
    t = re.sub(r"^[TB]\s*[-.]?\s*(?=\d)", "", t)  # "T2", "B-3"; no toca "BOSQUE"
    return t


def normalizar_numero(valor: str | int) -> str:
    """'apto 301' / '301.0' (Excel) -> '301'. 'PQ-05' se conserva."""
    n = " ".join(str(valor).split()).upper()
    n = re.sub(r"^(APARTAMENTO|APTO\.?|APT\.?|CASA|LOCAL)\s*", "", n)
    if re.fullmatch(r"\d+\.0+", n):  # Excel guarda 301 como 301.0
        n = n.split(".")[0]
    if not n:
        raise ValueError("El número de la unidad es obligatorio")
    if len(n) > 20:
        raise ValueError(f"El número de unidad «{valor}» es demasiado largo")
    return n


def etiqueta(torre: str, numero: str) -> str:
    return f"{torre}-{numero}" if torre else numero


def parsear_decimal(valor: str | int | float | Decimal) -> Decimal:
    """Acepta formato colombiano y de Excel: '0,8532', '0.8532', '1.234,5', '0,85 %', 0.8532."""
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, int | float):
        return Decimal(str(valor))
    s = valor.strip().replace("%", "").replace(" ", "")
    if "," in s and "." in s:  # '1.234,56' (miles con punto) o '1,234.56'
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        raise ValueError(f"«{valor}» no es un número") from None


def parsear_coeficiente(valor: str | int | float | Decimal) -> Decimal:
    """Coeficiente en porcentaje con 4 decimales (0 < c <= 100)."""
    c = parsear_decimal(valor)
    if not Decimal(0) < c <= Decimal(100):
        raise ValueError(f"El coeficiente {valor} debe ser mayor que 0 y máximo 100")
    return c.quantize(Decimal("0.0001"))


def parsear_tipo_documento(valor: str) -> TipoDocumentoIdentidad:
    """'C.C.' / 'cédula' / 'Cedula de ciudadania' -> CC."""
    v = sin_tildes(valor).upper().replace(".", "").replace(" ", "")
    alias = {
        "CC": "CC", "CEDULA": "CC", "CEDULADECIUDADANIA": "CC",
        "CE": "CE", "CEDULADEEXTRANJERIA": "CE",
        "NIT": "NIT",
        "PASAPORTE": "PASAPORTE", "PA": "PASAPORTE", "PAS": "PASAPORTE",
        "PPT": "PPT", "PEP": "PPT",
        "TI": "TI", "TARJETADEIDENTIDAD": "TI",
    }  # fmt: skip
    if v not in alias:
        raise ValueError(f"Tipo de documento «{valor}» no reconocido (use CC, CE, NIT, PASAPORTE, PPT o TI)")
    return TipoDocumentoIdentidad(alias[v])


def sin_tildes(valor: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", valor) if unicodedata.category(c) != "Mn")


# --- Coeficientes (Ley 675 de 2001: deben sumar 100 %) ---------------------------

TOLERANCIA_COEFICIENTES = Decimal("0.01")  # redondeos de la escritura


@dataclass(frozen=True)
class EstadoCoeficientes:
    suma: Decimal
    unidades_con_coeficiente: int
    unidades_sin_coeficiente: int

    @property
    def diferencia(self) -> Decimal:
        return self.suma - Decimal(100)

    @property
    def cuadra(self) -> bool:
        return self.unidades_sin_coeficiente == 0 and abs(self.diferencia) <= TOLERANCIA_COEFICIENTES

    @property
    def mensaje(self) -> str:
        if self.cuadra:
            return "Los coeficientes suman 100 %"
        partes = [f"Los coeficientes suman {self.suma:.4f} %".replace(".", ",")]
        if self.unidades_sin_coeficiente:
            partes.append(f"{self.unidades_sin_coeficiente} unidad(es) sin coeficiente")
        return "; ".join(partes)


def estado_coeficientes(coeficientes: Iterable[Decimal | None]) -> EstadoCoeficientes:
    suma, con, sin = Decimal(0), 0, 0
    for c in coeficientes:
        if c is None:
            sin += 1
        else:
            suma += c
            con += 1
    return EstadoCoeficientes(suma, con, sin)


# --- Ocupación sugerida a partir de los vínculos vigentes ------------------------


@dataclass(frozen=True)
class VinculoResumen:
    relacion: RelacionUnidad
    reside: bool


def ocupacion_sugerida(vinculos: Iterable[VinculoResumen]) -> OcupacionUnidad:
    """- Hay arrendatario vigente -> ARRENDADA.
    - Sin arrendatario y alguien reside (el propietario o su familia) -> PROPIETARIO.
    - Hay propietario pero nadie reside -> DESOCUPADA.
    - Sin propietario registrado -> SIN_INFORMACION."""
    vs = list(vinculos)
    if any(v.relacion == RelacionUnidad.ARRENDATARIO for v in vs):
        return OcupacionUnidad.ARRENDADA
    if not any(v.relacion == RelacionUnidad.PROPIETARIO for v in vs):
        return OcupacionUnidad.SIN_INFORMACION
    if any(v.reside for v in vs):
        return OcupacionUnidad.PROPIETARIO
    return OcupacionUnidad.DESOCUPADA


def validar_porcentajes_propiedad(porcentajes: Iterable[Decimal | None]) -> None:
    """Los copropietarios vigentes de una unidad no pueden pasar del 100 %."""
    total = sum((p for p in porcentajes if p is not None), Decimal(0))
    if total > Decimal(100):
        raise ValueError(f"Los porcentajes de propiedad suman {total} %, más del 100 %")
