"""Importación del censo desde Excel, en dos pasos: vista previa y confirmación.

1. `plantilla()` genera el .xlsx con las hojas Unidades, Personas y Vehículos.
2. `previsualizar()` lee el archivo y calcula QUÉ haría, sin guardar nada: unidades
   nuevas y cambios (antes → después), personas, vínculos, vehículos, errores por
   hoja y fila, y la suma de coeficientes resultante.
3. `aplicar()` recalcula el plan (el archivo se reenvía y se compara su hash con el
   de la vista previa) y lo ejecuta en UNA transacción a través de los mismos casos
   de uso de la pantalla (mismas validaciones, auditoría y RLS).

Reglas: la unidad se identifica por (torre, número) y la persona por (tipo, número
de documento), o por su nombre dentro de la misma unidad si no tiene documento.
Una celda vacía significa "no cambiar". Nada se desactiva por no venir en el
archivo, y reimportar el mismo archivo no duplica nada.
"""

import hashlib
import io
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ImportacionUnidades, Persona, UnidadPersona, Unit, Vehiculo
from app.models.enums import RelacionUnidad, TipoDocumentoIdentidad, TipoUnidad, TipoVehiculo
from app.schemas.unidades import PersonaIn, PersonaUpdate, UnidadIn, UnidadUpdate, VehiculoIn, VinculoIn
from app.services.comun import Actor, ValidacionError, exigir
from app.services.unidades import dominio as d
from app.services.unidades import gestion
from app.services.unidades.dominio import PUEDE_GESTIONAR

MAX_BYTES = 5 * 1024 * 1024
MAX_FILAS = 5000
AZUL = "1F3A5F"

# --- Columnas (encabezado visible, clave interna, alias aceptados) -----------------

COLUMNAS_UNIDADES = [
    ("Torre", "torre", ("torre", "bloque", "interior", "edificio")),
    ("Número", "numero", ("numero", "apto", "apartamento", "unidad", "casa", "no", "nro")),
    ("Tipo", "tipo", ("tipo", "tipo de unidad", "clase")),
    ("Coeficiente (%)", "coeficiente", ("coeficiente", "coeficiente %", "coeficiente de copropiedad", "coef")),
    ("Área (m²)", "area", ("area", "area m2", "area privada", "metros", "m2")),
    ("Matrícula inmobiliaria", "matricula", ("matricula", "matricula inmobiliaria", "folio")),
    (
        "Anexo de (unidad principal)",
        "principal",
        ("anexo de", "unidad principal", "anexo de unidad principal", "principal"),
    ),
    ("Observaciones", "observaciones", ("observaciones", "notas", "comentarios")),
]
COLUMNAS_PERSONAS = [
    ("Torre", "torre", ("torre", "bloque", "interior", "edificio")),
    ("Número", "numero", ("numero", "apto", "apartamento", "unidad", "casa", "no", "nro")),
    ("Relación", "relacion", ("relacion", "tipo", "calidad", "rol")),
    ("Nombre completo", "nombre", ("nombre completo", "nombre", "nombres y apellidos", "propietario", "residente")),
    ("Tipo de documento", "tipo_documento", ("tipo de documento", "tipo documento", "tipo doc", "td")),
    ("Número de documento", "documento", ("numero de documento", "documento", "cedula", "identificacion", "nit", "cc")),
    ("Teléfono", "telefono", ("telefono", "celular", "movil", "telefono celular")),
    ("Correo", "email", ("correo", "email", "correo electronico", "e-mail")),
    ("Reside (Sí/No)", "reside", ("reside", "vive", "reside si no", "habita")),
    (
        "Responsable de pago (Sí/No)",
        "pago",
        ("responsable de pago", "responsable de pago si no", "paga", "responsable"),
    ),
    ("% de propiedad", "porcentaje", ("% de propiedad", "porcentaje", "porcentaje de propiedad", "participacion")),
    ("Autoriza datos (Sí/No)", "autoriza", ("autoriza datos", "autoriza datos si no", "habeas data", "autorizacion")),
]
COLUMNAS_VEHICULOS = [
    ("Torre", "torre", ("torre", "bloque", "interior", "edificio")),
    ("Número", "numero", ("numero", "apto", "apartamento", "unidad", "casa", "no", "nro")),
    ("Placa", "placa", ("placa", "placas")),
    ("Tipo", "tipo", ("tipo", "tipo de vehiculo", "clase")),
    ("Marca", "marca", ("marca", "marca y linea", "modelo")),
    ("Color", "color", ("color",)),
]
HOJAS = {
    "unidades": (("unidades", "unidad", "inmuebles", "censo"), COLUMNAS_UNIDADES),
    "personas": (("personas", "propietarios", "residentes", "directorio", "copropietarios"), COLUMNAS_PERSONAS),
    "vehiculos": (("vehiculos", "vehiculo", "carros", "parqueaderos"), COLUMNAS_VEHICULOS),
}

_TIPOS_UNIDAD = {
    "apartamento": "APARTAMENTO", "apto": "APARTAMENTO", "apt": "APARTAMENTO", "casa": "CASA",
    "local": "LOCAL", "local comercial": "LOCAL", "oficina": "OFICINA", "consultorio": "OFICINA",
    "parqueadero": "PARQUEADERO", "garaje": "PARQUEADERO", "parqueo": "PARQUEADERO",
    "deposito": "DEPOSITO", "cuarto util": "DEPOSITO", "util": "DEPOSITO", "bodega": "DEPOSITO", "otro": "OTRO",
}  # fmt: skip
_RELACIONES = {
    "propietario": "PROPIETARIO", "propietaria": "PROPIETARIO", "dueno": "PROPIETARIO", "copropietario": "PROPIETARIO",
    "arrendatario": "ARRENDATARIO", "arrendataria": "ARRENDATARIO", "inquilino": "ARRENDATARIO",
    "residente": "RESIDENTE", "familiar": "RESIDENTE", "ocupante": "RESIDENTE",
    "autorizado": "AUTORIZADO", "autorizada": "AUTORIZADO",
}  # fmt: skip
_TIPOS_VEHICULO = {
    "carro": "CARRO", "automovil": "CARRO", "auto": "CARRO", "camioneta": "CARRO", "moto": "MOTO",
    "motocicleta": "MOTO", "bicicleta": "BICICLETA", "bici": "BICICLETA", "otro": "OTRO",
}  # fmt: skip
_SI = {"si", "s", "x", "1", "true", "verdadero", "yes"}
_NO = {"no", "n", "0", "false", "falso"}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _clave(texto: Any) -> str:
    """Encabezados y valores de lista comparables: sin tildes, minúsculas, sin signos."""
    t = d.sin_tildes(str(texto)).lower()
    t = re.sub(r"[()\[\]/:%.²]", " ", t)
    return " ".join(t.split())


# --- Resultado de la vista previa ----------------------------------------------------


@dataclass
class ErrorFila:
    hoja: str
    fila: int
    mensaje: str


@dataclass
class _UnidadPlan:
    fila: int
    torre: str
    numero: str
    datos: dict[str, Any]  # solo columnas con valor
    principal: tuple[str, str] | None = None
    existente: Unit | None = None
    cambios: dict[str, tuple[Any, Any]] = field(default_factory=dict)

    @property
    def etiqueta(self) -> str:
        return d.etiqueta(self.torre, self.numero)


@dataclass
class _PersonaPlan:
    fila: int
    unidad: tuple[str, str]
    relacion: RelacionUnidad
    nombre: str
    tipo_documento: TipoDocumentoIdentidad | None
    documento: str | None
    telefono: str | None
    email: str | None
    reside: bool | None
    pago: bool | None
    porcentaje: Decimal | None
    autoriza: bool | None
    existente: Persona | None = None
    cambios: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    vinculo_existe: bool = False
    clave_persona: str = ""


@dataclass
class _VehiculoPlan:
    fila: int
    unidad: tuple[str, str]
    placa: str
    tipo: TipoVehiculo
    marca: str | None
    color: str | None
    existe: bool = False


@dataclass
class Plan:
    archivo: str
    sha256: str
    filas_leidas: int = 0
    unidades: list[_UnidadPlan] = field(default_factory=list)
    personas: list[_PersonaPlan] = field(default_factory=list)
    vehiculos: list[_VehiculoPlan] = field(default_factory=list)
    errores: list[ErrorFila] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)
    coeficientes: d.EstadoCoeficientes | None = None

    def error(self, hoja: str, fila: int, mensaje: str) -> None:
        self.errores.append(ErrorFila(hoja, fila, mensaje))

    @property
    def unidades_nuevas(self) -> list[_UnidadPlan]:
        return [u for u in self.unidades if u.existente is None]

    @property
    def unidades_con_cambios(self) -> list[_UnidadPlan]:
        return [u for u in self.unidades if u.existente is not None and u.cambios]

    @property
    def personas_nuevas(self) -> int:
        return len({p.clave_persona for p in self.personas if p.existente is None})

    @property
    def personas_con_cambios(self) -> int:
        return len({p.clave_persona for p in self.personas if p.existente is not None and p.cambios})

    @property
    def vinculos_nuevos(self) -> list[_PersonaPlan]:
        return [p for p in self.personas if not p.vinculo_existe]

    @property
    def vehiculos_nuevos(self) -> list[_VehiculoPlan]:
        return [v for v in self.vehiculos if not v.existe]

    def a_json(self) -> dict[str, Any]:
        def valor(v: Any) -> Any:
            if isinstance(v, Decimal):
                return str(v)
            if hasattr(v, "value"):
                return v.value
            return v

        return {
            "archivo": self.archivo,
            "sha256": self.sha256,
            "filas_leidas": self.filas_leidas,
            "puede_aplicar": not self.errores and self.hay_cambios,
            "hay_cambios": self.hay_cambios,
            "totales": {
                "unidades_nuevas": len(self.unidades_nuevas),
                "unidades_con_cambios": len(self.unidades_con_cambios),
                "personas_nuevas": self.personas_nuevas,
                "personas_con_cambios": self.personas_con_cambios,
                "vinculos_nuevos": len(self.vinculos_nuevos),
                "vehiculos_nuevos": len(self.vehiculos_nuevos),
                "sin_cambios": sum(1 for u in self.unidades if u.existente is not None and not u.cambios)
                + sum(1 for p in self.personas if p.vinculo_existe and not p.cambios)
                + sum(1 for v in self.vehiculos if v.existe),
            },
            "unidades_nuevas": [
                {"fila": u.fila, "etiqueta": u.etiqueta, **{k: valor(v) for k, v in u.datos.items()}}
                for u in self.unidades_nuevas[:500]
            ],
            "unidades_con_cambios": [
                {
                    "fila": u.fila,
                    "etiqueta": u.etiqueta,
                    "cambios": {k: {"antes": valor(a), "despues": valor(b)} for k, (a, b) in u.cambios.items()},
                }
                for u in self.unidades_con_cambios[:500]
            ],
            "vinculos_nuevos": [
                {
                    "fila": p.fila,
                    "unidad": d.etiqueta(*p.unidad),
                    "nombre": p.nombre,
                    "relacion": p.relacion.value,
                    "persona_nueva": p.existente is None,
                }
                for p in self.vinculos_nuevos[:500]
            ],
            "vehiculos_nuevos": [
                {"fila": v.fila, "unidad": d.etiqueta(*v.unidad), "placa": v.placa, "tipo": v.tipo.value}
                for v in self.vehiculos_nuevos[:500]
            ],
            "errores": [{"hoja": e.hoja, "fila": e.fila, "mensaje": e.mensaje} for e in self.errores[:500]],
            "total_errores": len(self.errores),
            "advertencias": self.advertencias,
            "coeficientes": None
            if self.coeficientes is None
            else {
                "suma": str(self.coeficientes.suma),
                "cuadra": self.coeficientes.cuadra,
                "mensaje": self.coeficientes.mensaje,
            },
        }

    @property
    def hay_cambios(self) -> bool:
        return bool(
            self.unidades_nuevas
            or self.unidades_con_cambios
            or self.vinculos_nuevos
            or self.vehiculos_nuevos
            or any(p.cambios for p in self.personas)
        )


# --- Plantilla ---------------------------------------------------------------------


def plantilla() -> bytes:
    wb = Workbook()
    ins = wb.active
    ins.title = "Instrucciones"
    lineas = [
        ("Importar el censo de la copropiedad", True),
        ("", False),
        ("1. Llene las hojas Unidades, Personas y Vehículos. Puede dejar vacías las que no necesite.", False),
        ("2. Cada unidad se identifica por Torre + Número. Si el conjunto no tiene torres, deje Torre vacía.", False),
        ("3. Una celda vacía significa «no cambiar»: puede reimportar el archivo para completar datos.", False),
        ("4. Los parqueaderos y depósitos privados se registran como unidades con «Anexo de» = la unidad", False),
        (
            "   principal (por ejemplo 1-101). Si su coeficiente está incluido en el del apartamento, déjelo vacío.",
            False,
        ),
        ("5. Coeficientes en porcentaje: 0,8532 significa 0,8532 %. Deben sumar 100 %.", False),
        ("6. En Personas va una fila por cada persona y unidad. Una misma persona puede aparecer en varias.", False),
        (
            "7. Al subir el archivo verá una vista previa con los cambios y errores. Nada se guarda hasta confirmar.",
            False,
        ),
        ("", False),
        ("Relación: Propietario, Arrendatario, Residente (familiar u ocupante) o Autorizado.", False),
        ("Tipo de documento: CC, CE, NIT, PASAPORTE, PPT o TI.", False),
        ("Autoriza datos: autorización de tratamiento de datos personales (Ley 1581 de 2012).", False),
    ]
    for i, (texto, negrita) in enumerate(lineas, start=1):
        ins.cell(row=i, column=1, value=texto).font = Font(
            bold=negrita, size=14 if negrita else 11, color=AZUL if negrita else None
        )
    ins.column_dimensions["A"].width = 110

    ejemplos = {
        "Unidades": (
            COLUMNAS_UNIDADES,
            [
                ["1", "101", "Apartamento", 1.2345, 62.5, "50C-1234567", None, None],
                ["1", "PQ-01", "Parqueadero", None, 12, None, "1-101", "Cubierto"],
            ],
            {3: list(_TITULOS_TIPO_UNIDAD)},
        ),
        "Personas": (
            COLUMNAS_PERSONAS,
            [
                ["1", "101", "Propietario", "Ana María Gómez", "CC", "1020304050", "3001234567", "ana@correo.com", "Sí", "Sí", None, "Sí"],
                ["1", "101", "Residente", "Tomás Gómez", "TI", "1098765432", None, None, "Sí", "No", None, "No"],
            ],
            {3: ["Propietario", "Arrendatario", "Residente", "Autorizado"], 5: [t.value for t in TipoDocumentoIdentidad], 9: ["Sí", "No"], 10: ["Sí", "No"], 12: ["Sí", "No"]},
        ),
        "Vehículos": (
            COLUMNAS_VEHICULOS,
            [["1", "101", "ABC123", "Carro", "Mazda 3", "Gris"]],
            {4: ["Carro", "Moto", "Bicicleta", "Otro"]},
        ),
    }  # fmt: skip
    for titulo, (columnas, filas, listas) in ejemplos.items():
        ws = wb.create_sheet(titulo)
        for c, (encabezado, _, _) in enumerate(columnas, start=1):
            celda = ws.cell(row=1, column=c, value=encabezado)
            celda.font = Font(bold=True, color="FFFFFF")
            celda.fill = PatternFill("solid", fgColor=AZUL)
            celda.alignment = Alignment(vertical="center")
            ws.column_dimensions[get_column_letter(c)].width = max(14, len(encabezado) + 4)
        for fila in filas:
            ws.append(fila)
        for col, opciones in listas.items():
            dv = DataValidation(type="list", formula1='"' + ",".join(opciones) + '"', allow_blank=True)
            dv.error, dv.errorTitle = "Elija un valor de la lista", "Valor no válido"
            ws.add_data_validation(dv)
            letra = get_column_letter(col)
            dv.add(f"{letra}2:{letra}{MAX_FILAS}")
        ws.freeze_panes = "A2"
        # Texto en Torre, Número y documento: Excel no debe convertir "0101" en 101
        for col in [1, 2] + ([6] if titulo == "Personas" else []):
            for r in range(2, 1001):
                ws.cell(row=r, column=col).number_format = "@"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_TITULOS_TIPO_UNIDAD = ("Apartamento", "Casa", "Local", "Oficina", "Parqueadero", "Depósito", "Otro")


# --- Lectura -----------------------------------------------------------------------


def _texto(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, datetime | date):
        return v.strftime("%d/%m/%Y")
    s = " ".join(str(v).split())
    return s or None


def _bool(v: Any) -> bool | None:
    s = _texto(v)
    if s is None:
        return None
    k = _clave(s)
    if k in _SI:
        return True
    if k in _NO:
        return False
    raise ValueError(f"«{s}» no es Sí o No")


def _lista(v: str, opciones: dict[str, str], que: str) -> str:
    k = _clave(v)
    if k not in opciones:
        raise ValueError(f"{que} «{v}» no reconocido")
    return opciones[k]


def _leer_hojas(contenido: bytes, plan: Plan) -> dict[str, list[tuple[int, dict[str, Any]]]]:
    try:
        wb = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 - openpyxl lanza varios tipos según el daño del archivo
        raise ValidacionError("El archivo no es un Excel válido (.xlsx)") from None
    resultado: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    por_nombre = {_clave(ws.title): ws for ws in wb.worksheets}
    for clave, (alias, columnas) in HOJAS.items():
        ws = next((por_nombre[a] for a in alias if a in por_nombre), None)
        if ws is None:
            continue
        filas = ws.iter_rows(values_only=True)
        encabezado = next(filas, None)
        if not encabezado:
            continue
        mapa: dict[int, str] = {}
        for i, h in enumerate(encabezado):
            if h is None:
                continue
            k = _clave(h)
            for _, interna, aliases in columnas:
                if k in aliases and interna not in mapa.values():
                    mapa[i] = interna
                    break
        if "numero" not in mapa.values():  # Torre es opcional (conjuntos sin torres)
            plan.error(ws.title, 1, "Falta la columna Número")
            continue
        registros: list[tuple[int, dict[str, Any]]] = []
        for n, fila in enumerate(filas, start=2):
            if n > MAX_FILAS + 1:
                plan.error(ws.title, n, f"El archivo supera el máximo de {MAX_FILAS} filas por hoja")
                break
            datos = {mapa[i]: v for i, v in enumerate(fila) if i in mapa and _texto(v) is not None}
            if datos:
                registros.append((n, datos))
        resultado[clave] = registros
        plan.filas_leidas += len(registros)
    if not resultado:
        raise ValidacionError("No se encontraron las hojas Unidades, Personas o Vehículos. Use la plantilla.")
    return resultado


def _clave_unidad(datos: dict[str, Any]) -> tuple[str, str]:
    return d.normalizar_torre(_texto(datos.get("torre"))), d.normalizar_numero(_texto(datos["numero"]) or "")


def _parse_etiqueta(texto: str, unidades: dict[tuple[str, str], Any]) -> tuple[str, str] | None:
    """'1-101' / 'T1 101' / '101' -> (torre, número) de una unidad conocida, o None."""
    t = texto.strip().upper()
    candidatos = [("", t)] + [tuple(t.split(sep, 1)) for sep in ("-", " ", "/") if sep in t]
    for torre, numero in candidatos:
        try:
            k = (d.normalizar_torre(torre), d.normalizar_numero(numero))
        except ValueError:
            continue
        if k in unidades:
            return k
    return None


# --- Plan --------------------------------------------------------------------------


async def previsualizar(db: AsyncSession, actor: Actor, nombre: str, contenido: bytes) -> Plan:
    exigir(actor, PUEDE_GESTIONAR, "importar el censo")
    if len(contenido) > MAX_BYTES:
        raise ValidacionError("El archivo supera 5 MB")
    plan = Plan(archivo=nombre, sha256=hashlib.sha256(contenido).hexdigest())
    hojas = _leer_hojas(contenido, plan)

    existentes = {(u.tower, u.number): u for u in await db.scalars(select(Unit))}
    await _plan_unidades(plan, hojas.get("unidades", []), existentes)
    conocidas: dict[tuple[str, str], Any] = {**existentes, **{(u.torre, u.numero): u for u in plan.unidades_nuevas}}
    await _plan_personas(db, plan, hojas.get("personas", []), existentes, conocidas)
    await _plan_vehiculos(db, plan, hojas.get("vehiculos", []), existentes, conocidas)
    _plan_coeficientes(plan, existentes)
    return plan


_CAMPOS_UNIDAD = {
    "tipo": "tipo",
    "coeficiente": "coefficient",
    "area": "area_m2",
    "matricula": "matricula_inmobiliaria",
    "observaciones": "observaciones",
}


async def _plan_unidades(
    plan: Plan, filas: list[tuple[int, dict[str, Any]]], existentes: dict[tuple[str, str], Unit]
) -> None:
    hoja = "Unidades"
    vistas: dict[tuple[str, str], int] = {}
    for n, datos in filas:
        try:
            if "numero" not in datos:
                raise ValueError("Falta el número de la unidad")
            torre, numero = _clave_unidad(datos)
            valores: dict[str, Any] = {}
            if "tipo" in datos:
                valores["tipo"] = TipoUnidad(_lista(_texto(datos["tipo"]) or "", _TIPOS_UNIDAD, "Tipo de unidad"))
            if "coeficiente" in datos:
                valores["coefficient"] = d.parsear_coeficiente(datos["coeficiente"])
            if "area" in datos:
                area = d.parsear_decimal(datos["area"])
                if area <= 0:
                    raise ValueError("El área debe ser mayor que 0")
                valores["area_m2"] = area.quantize(Decimal("0.01"))
            if "matricula" in datos:
                valores["matricula_inmobiliaria"] = (_texto(datos["matricula"]) or "").upper().replace(" ", "")
            if "observaciones" in datos:
                valores["observaciones"] = _texto(datos["observaciones"])
        except ValueError as e:
            plan.error(hoja, n, str(e))
            continue
        if (torre, numero) in vistas:
            plan.error(
                hoja,
                n,
                f"La unidad {d.etiqueta(torre, numero)} está repetida (también en la fila {vistas[(torre, numero)]})",
            )
            continue
        vistas[(torre, numero)] = n
        up = _UnidadPlan(n, torre, numero, valores, existente=existentes.get((torre, numero)))
        if "principal" in datos:
            up.datos["_principal_texto"] = _texto(datos["principal"])
        plan.unidades.append(up)

    # Segunda pasada: anexos (pueden apuntar a unidades nuevas del mismo archivo)
    en_archivo = {(u.torre, u.numero): u for u in plan.unidades}
    conocidas: dict[tuple[str, str], Any] = {**existentes, **en_archivo}
    matriculas = {u.matricula_inmobiliaria: u.etiqueta for u in existentes.values() if u.matricula_inmobiliaria}

    def es_anexo(k: tuple[str, str]) -> bool:
        if k in en_archivo and en_archivo[k].datos.get("_principal_texto"):
            return True
        return k in existentes and existentes[k].unidad_principal_id is not None

    for up in plan.unidades:
        texto = up.datos.get("_principal_texto")
        if texto:
            k = _parse_etiqueta(texto, conocidas)
            if k is None:
                plan.error(hoja, up.fila, f"La unidad principal {texto} no existe ni está en el archivo")
                continue
            if k == (up.torre, up.numero):
                plan.error(hoja, up.fila, "Una unidad no puede ser anexo de sí misma")
                continue
            if es_anexo(k):
                plan.error(hoja, up.fila, f"{texto} es un anexo: elija la unidad principal")
                continue
            up.principal = k
        mat = up.datos.get("matricula_inmobiliaria")
        if mat:
            dueno = matriculas.get(mat)
            if dueno and dueno != up.etiqueta:
                plan.error(hoja, up.fila, f"La matrícula {mat} ya está en la unidad {dueno}")
                continue
            matriculas[mat] = up.etiqueta
        if up.existente is not None:
            u = up.existente
            for campo, valor in up.datos.items():
                if campo.startswith("_"):
                    continue
                if getattr(u, campo) != valor:
                    up.cambios[campo] = (getattr(u, campo), valor)
            if up.principal is not None:
                actual = (
                    next((k for k, x in existentes.items() if x.id == u.unidad_principal_id), None)
                    if u.unidad_principal_id
                    else None
                )
                if actual != up.principal:
                    up.cambios["unidad_principal"] = (
                        d.etiqueta(*actual) if actual else None,
                        d.etiqueta(*up.principal),
                    )
            if not u.activa:
                plan.error(
                    hoja, up.fila, f"La unidad {u.etiqueta} está desactivada: reactívela antes de importar cambios"
                )
    for up in plan.unidades:
        up.datos.pop("_principal_texto", None)


async def _plan_personas(
    db: AsyncSession,
    plan: Plan,
    filas: list[tuple[int, dict[str, Any]]],
    existentes: dict[tuple[str, str], Unit],
    conocidas: dict[tuple[str, str], Any],
) -> None:
    hoja = "Personas"
    personas = list(await db.scalars(select(Persona)))
    por_doc = {(p.tipo_documento, p.numero_documento): p for p in personas if p.numero_documento}
    por_id = {p.id: p for p in personas}
    vigentes = list(await db.scalars(select(UnidadPersona).where(UnidadPersona.fecha_fin.is_(None))))
    unidad_por_id = {u.id: k for k, u in existentes.items()}
    vinc_por_unidad: dict[tuple[str, str], list[UnidadPersona]] = {}
    for v in vigentes:
        k = unidad_por_id.get(v.unidad_id)
        if k:
            vinc_por_unidad.setdefault(k, []).append(v)

    en_archivo: dict[str, int] = {}  # clave de persona -> primera fila (para no duplicarla)
    vistos: set[tuple[tuple[str, str], str, RelacionUnidad]] = set()
    pago_por_unidad: dict[tuple[str, str], int] = {}
    for n, datos in filas:
        try:
            if "numero" not in datos:
                raise ValueError("Falta el número de la unidad")
            unidad = _clave_unidad(datos)
            if unidad not in conocidas:
                raise ValueError(f"La unidad {d.etiqueta(*unidad)} no existe ni está en la hoja Unidades")
            if "relacion" not in datos:
                raise ValueError("Falta la relación (Propietario, Arrendatario, Residente o Autorizado)")
            relacion = RelacionUnidad(_lista(_texto(datos["relacion"]) or "", _RELACIONES, "Relación"))
            if "nombre" not in datos:
                raise ValueError("Falta el nombre completo")
            nombre = d.normalizar_nombre(_texto(datos["nombre"]) or "")
            tipo_doc = (
                d.parsear_tipo_documento(_texto(datos["tipo_documento"]) or "") if "tipo_documento" in datos else None
            )
            documento = d.normalizar_documento(_texto(datos["documento"]) or "") if "documento" in datos else None
            if documento and tipo_doc is None:
                tipo_doc = TipoDocumentoIdentidad.CC  # lo más común; se avisa
                plan.advertencias.append(f"Personas, fila {n}: sin tipo de documento, se asumió CC")
            if tipo_doc and not documento:
                raise ValueError("Indicó el tipo de documento pero no el número")
            telefono = d.normalizar_telefono(_texto(datos["telefono"]) or "") if "telefono" in datos else None
            email = (_texto(datos.get("email")) or "").lower() or None
            if email and not _EMAIL.fullmatch(email):
                raise ValueError(f"El correo «{email}» no es válido")
            porcentaje = None
            if "porcentaje" in datos:
                porcentaje = d.parsear_decimal(datos["porcentaje"]).quantize(Decimal("0.01"))
                if not Decimal(0) < porcentaje <= Decimal(100):
                    raise ValueError("El % de propiedad debe estar entre 0 y 100")
                if relacion != RelacionUnidad.PROPIETARIO:
                    raise ValueError("El % de propiedad solo aplica a propietarios")
            pago = _bool(datos.get("pago"))
            if pago and relacion == RelacionUnidad.AUTORIZADO:
                raise ValueError("Un autorizado no puede ser el responsable del pago")
            pp = _PersonaPlan(
                n, unidad, relacion, nombre, tipo_doc, documento, telefono, email,
                _bool(datos.get("reside")), pago, porcentaje, _bool(datos.get("autoriza")),
            )  # fmt: skip
        except ValueError as e:
            plan.error(hoja, n, str(e))
            continue
        if pp.pago:
            if unidad in pago_por_unidad:
                plan.error(
                    hoja, n, f"{d.etiqueta(*unidad)} ya tiene responsable de pago en la fila {pago_por_unidad[unidad]}"
                )
                continue
            pago_por_unidad[unidad] = n

        # ¿Quién es? Por documento, o por nombre entre las personas vigentes de la unidad
        if documento:
            pp.clave_persona = f"doc:{tipo_doc}:{documento}"
            pp.existente = por_doc.get((tipo_doc, documento))
        else:
            pp.clave_persona = f"nombre:{d.etiqueta(*unidad)}:{_clave(nombre)}"
            for v in vinc_por_unidad.get(unidad, []):
                p = por_id.get(v.persona_id)
                if p and _clave(p.nombre_completo) == _clave(nombre):
                    pp.existente = p
                    break
        clave_vinculo = (unidad, pp.clave_persona, relacion)
        if clave_vinculo in vistos:
            plan.error(hoja, n, f"{nombre} ya figura como {relacion.lower()} de {d.etiqueta(*unidad)} en otra fila")
            continue
        vistos.add(clave_vinculo)

        if pp.existente is not None:
            p = pp.existente
            if not p.activa:
                plan.error(hoja, n, f"{p.nombre_completo} está desactivada en la plataforma")
                continue
            if _clave(p.nombre_completo) != _clave(nombre):
                plan.advertencias.append(
                    f"Personas, fila {n}: el documento {documento} pertenece a «{p.nombre_completo}»; se conserva ese nombre"
                )
            if pp.clave_persona not in en_archivo:  # los cambios de datos se toman de la primera fila
                for campo, nuevo in (("telefono", telefono), ("email", email)):
                    if nuevo and getattr(p, campo) != nuevo:
                        pp.cambios[campo] = (getattr(p, campo), nuevo)
                if pp.autoriza and p.autoriza_datos_at is None:
                    pp.cambios["autoriza_datos"] = (False, True)
            pp.vinculo_existe = any(
                v.persona_id == p.id and v.relacion == relacion for v in vinc_por_unidad.get(unidad, [])
            )
        en_archivo.setdefault(pp.clave_persona, n)
        plan.personas.append(pp)

    # Porcentajes de propiedad por unidad (vigentes + nuevos)
    for unidad in {p.unidad for p in plan.personas if p.porcentaje is not None}:
        actuales = [
            v.porcentaje_propiedad for v in vinc_por_unidad.get(unidad, []) if v.relacion == RelacionUnidad.PROPIETARIO
        ]
        nuevos = [p.porcentaje for p in plan.personas if p.unidad == unidad and not p.vinculo_existe]
        try:
            d.validar_porcentajes_propiedad(actuales + nuevos)
        except ValueError as e:
            fila = next(p.fila for p in plan.personas if p.unidad == unidad and p.porcentaje is not None)
            plan.error(hoja, fila, f"{d.etiqueta(*unidad)}: {e}")


async def _plan_vehiculos(
    db: AsyncSession,
    plan: Plan,
    filas: list[tuple[int, dict[str, Any]]],
    existentes: dict[tuple[str, str], Unit],
    conocidas: dict[tuple[str, str], Any],
) -> None:
    hoja = "Vehículos"
    activos = {v.placa: v for v in await db.scalars(select(Vehiculo).where(Vehiculo.activo))}
    unidad_por_id = {u.id: k for k, u in existentes.items()}
    vistas: dict[str, int] = {}
    for n, datos in filas:
        try:
            if "numero" not in datos:
                raise ValueError("Falta el número de la unidad")
            unidad = _clave_unidad(datos)
            if unidad not in conocidas:
                raise ValueError(f"La unidad {d.etiqueta(*unidad)} no existe ni está en la hoja Unidades")
            if "placa" not in datos:
                raise ValueError("Falta la placa")
            placa = d.normalizar_placa(_texto(datos["placa"]) or "")
            tipo = (
                TipoVehiculo(_lista(_texto(datos["tipo"]) or "", _TIPOS_VEHICULO, "Tipo de vehículo"))
                if "tipo" in datos
                else TipoVehiculo.CARRO
            )
        except ValueError as e:
            plan.error(hoja, n, str(e))
            continue
        if placa in vistas:
            plan.error(hoja, n, f"La placa {placa} está repetida (también en la fila {vistas[placa]})")
            continue
        vistas[placa] = n
        vp = _VehiculoPlan(n, unidad, placa, tipo, _texto(datos.get("marca")), _texto(datos.get("color")))
        actual = activos.get(placa)
        if actual is not None:
            donde = unidad_por_id.get(actual.unidad_id)
            if donde != unidad:
                plan.error(
                    hoja, n, f"La placa {placa} ya está registrada en {d.etiqueta(*donde) if donde else 'otra unidad'}"
                )
                continue
            vp.existe = True
        plan.vehiculos.append(vp)


def _plan_coeficientes(plan: Plan, existentes: dict[tuple[str, str], Unit]) -> None:
    resultado: dict[tuple[str, str], tuple[Decimal | None, bool]] = {
        k: (u.coefficient, u.unidad_principal_id is not None) for k, u in existentes.items() if u.activa
    }
    hay_coeficientes = False
    for up in plan.unidades:
        k = (up.torre, up.numero)
        coef, anexo = resultado.get(k, (None, False))
        if "coefficient" in up.datos:
            coef = up.datos["coefficient"]
            hay_coeficientes = True
        resultado[k] = (coef, anexo or up.principal is not None)
    if not hay_coeficientes and not plan.unidades_nuevas:
        return
    plan.coeficientes = d.estado_coeficientes(c for c, anexo in resultado.values() if not (anexo and c is None))
    if not plan.coeficientes.cuadra:
        plan.advertencias.append(plan.coeficientes.mensaje + " (la Ley 675 exige que sumen 100 %)")


# --- Aplicar -----------------------------------------------------------------------


async def aplicar(db: AsyncSession, actor: Actor, nombre: str, contenido: bytes, sha256: str) -> ImportacionUnidades:
    plan = await previsualizar(db, actor, nombre, contenido)
    if plan.sha256 != sha256:
        raise ValidacionError("El archivo no coincide con el de la vista previa: vuelva a cargarlo")
    if plan.errores:
        raise ValidacionError(f"El archivo tiene {len(plan.errores)} error(es): corríjalos antes de importar")
    if not plan.hay_cambios:
        raise ValidacionError("El archivo no trae cambios: todo ya está registrado")
    motivo = f"Importación de Excel: {nombre}"[:1000]
    # (torre, número) -> id, incluidas las que se van creando (los anexos apuntan a ellas)
    ids: dict[tuple[str, str], uuid.UUID] = {(u.tower, u.number): u.id for u in await db.scalars(select(Unit))}

    # 1) Unidades nuevas: primero las principales, luego los anexos
    for up in sorted(plan.unidades_nuevas, key=lambda x: x.principal is not None):
        u = await gestion.crear_unidad(
            db,
            actor,
            UnidadIn(
                tower=up.torre,
                number=up.numero,
                unidad_principal_id=ids[up.principal] if up.principal else None,
                **up.datos,
            ),
        )
        ids[(up.torre, up.numero)] = u.id
    # 2) Cambios en unidades existentes
    for up in plan.unidades_con_cambios:
        cambios = {k: b for k, (_, b) in up.cambios.items() if k != "unidad_principal"}
        if "unidad_principal" in up.cambios and up.principal:
            cambios["unidad_principal_id"] = ids[up.principal]
        await gestion.editar_unidad(db, actor, up.existente.id, UnidadUpdate(**cambios, motivo=motivo))  # type: ignore[union-attr]

    # 3) Personas (una sola vez cada una) y vínculos
    unidades = ids
    creadas: dict[str, uuid.UUID] = {}
    actualizadas: set[str] = set()
    vinculos = 0
    for pp in plan.personas:
        if pp.existente is not None:
            persona_id = pp.existente.id
            if pp.cambios and pp.clave_persona not in actualizadas:
                await gestion.editar_persona(
                    db,
                    actor,
                    persona_id,
                    PersonaUpdate(
                        **{k: b for k, (_, b) in pp.cambios.items() if k != "autoriza_datos"},
                        autoriza_datos=True if "autoriza_datos" in pp.cambios else None,
                        motivo=motivo,
                    ),
                )
                actualizadas.add(pp.clave_persona)
        elif pp.clave_persona in creadas:
            persona_id = creadas[pp.clave_persona]
        else:
            p = await gestion.crear_persona(
                db,
                actor,
                PersonaIn(
                    nombre_completo=pp.nombre,
                    tipo_documento=pp.tipo_documento,
                    numero_documento=pp.documento,
                    telefono=pp.telefono,
                    email=pp.email,
                    autoriza_datos=bool(pp.autoriza),
                ),
            )
            persona_id = creadas[pp.clave_persona] = p.id
        if pp.vinculo_existe:
            continue
        await gestion.vincular(
            db,
            actor,
            unidades[pp.unidad],
            VinculoIn(
                persona_id=persona_id,
                relacion=pp.relacion,
                porcentaje_propiedad=pp.porcentaje,
                responsable_pago=pp.pago,
                reside=bool(pp.reside),
            ),
        )
        vinculos += 1

    # 4) Vehículos
    for vp in plan.vehiculos_nuevos:
        await gestion.registrar_vehiculo(
            db, actor, unidades[vp.unidad], VehiculoIn(placa=vp.placa, tipo=vp.tipo, marca=vp.marca, color=vp.color)
        )

    registro = ImportacionUnidades(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        usuario_id=actor.user_id,
        archivo_nombre=nombre[:255],
        sha256=plan.sha256,
        filas_leidas=plan.filas_leidas,
        unidades_creadas=len(plan.unidades_nuevas),
        unidades_actualizadas=len(plan.unidades_con_cambios),
        personas_creadas=len(creadas),
        personas_actualizadas=len(actualizadas),
        vinculos_creados=vinculos,
        vehiculos_creados=len(plan.vehiculos_nuevos),
        advertencias=plan.advertencias,
    )
    db.add(registro)
    await db.flush()
    return registro
