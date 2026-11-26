"""Conciliación de pagos de cuotas con el extracto bancario.

1. `leer_extracto`: lee el Excel (.xlsx) o CSV que exporta el banco, detecta las columnas (fecha, descripción,
   referencia, valor o crédito/débito, pagador) sin importar el banco y devuelve solo las entradas de dinero.
2. `sugerir`: para cada movimiento propone la unidad que pagó, con una confianza y los motivos: la unidad mencionada
   en la referencia o descripción («APTO 502», «T1-502»), el valor que coincide con lo que debe una sola unidad
   (saldo, cuota del mes o cuota con descuento) y el nombre del pagador. Marca como «ya registrado» lo que ya está.
3. `registrar`: registra los pagos confirmados con el mismo servicio de siempre (intereses primero, luego lo más
   antiguo; recibo numerado). Nada se guarda antes de este paso.

La referencia de cada movimiento es estable (la del banco o una calculada con fecha, valor y descripción), así que
subir el mismo extracto dos veces nunca duplica pagos: el registro rechaza referencias repetidas.
"""

import csv
import hashlib
import io
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CargoCartera, PagoCartera, PeriodoCartera, Persona, SaldoCargo, UnidadPersona, Unit
from app.models.enums import EstadoCargo, EstadoPagoCartera, MedioPago
from app.schemas.cartera import PagoIn
from app.services.cartera import pagos
from app.services.cartera.dominio import PUEDE_REGISTRAR_PAGO
from app.services.comun import Actor, NoEncontrado, ValidacionError, exigir

MAX_BYTES = 5 * 1024 * 1024
MAX_MOVIMIENTOS = 3000


# --------------------------------------------------------------------------------------------- lectura
@dataclass
class MovimientoBanco:
    fila: int
    fecha: date
    descripcion: str
    referencia: str | None
    pagador: str | None
    valor: Decimal


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


def parse_monto(v: object) -> Decimal | None:
    """Montos como los exportan los bancos: 1.234.567,89 · 1,234,567.89 · $ 450.000 · (12.000) · -12000."""
    if v is None or v == "":
        return None
    if isinstance(v, int | float | Decimal):
        return Decimal(str(v))
    s = str(v).strip().replace("$", "").replace("COP", "").replace(" ", "")
    negativo = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    s = s.strip("-()")
    if not s or not re.fullmatch(r"[\d.,]+", s):
        return None
    if "," in s and "." in s:
        decimal_sep = "," if s.rfind(",") > s.rfind(".") else "."
        miles = "." if decimal_sep == "," else ","
        s = s.replace(miles, "").replace(decimal_sep, ".")
    elif "," in s:
        partes = s.split(",")
        s = s.replace(",", "") if len(partes[-1]) == 3 and len(partes) > 1 else s.replace(",", ".")
    elif s.count(".") > 1 or (len(s.split(".")[-1]) == 3 and "." in s):
        s = s.replace(".", "")  # 450.000 o 1.234.567: puntos de miles
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return -d if negativo else d


def parse_fecha(v: object) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if v is None:
        return None
    s = str(v).strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y%m%d", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


_COLUMNAS = {
    "fecha": ("fecha",),
    "descripcion": ("descrip", "concepto", "detalle", "transacc", "movimiento", "glosa"),
    "referencia": ("referencia", "ref", "documento", "dcto", "comprobante", "numero", "no. doc"),
    "pagador": ("nombre", "tercero", "ordenante", "originador", "pagador", "remitente"),
    "credito": ("credito", "abono", "ingreso", "deposito", "entrada"),
    "debito": ("debito", "cargo", "retiro", "egreso", "salida"),
    "valor": ("valor", "monto", "importe"),
}


def _mapear(cabecera: list[object]) -> dict[str, int] | None:
    nombres = [normalizar(c) if c is not None else "" for c in cabecera]
    mapa: dict[str, int] = {}
    for clave, pistas in _COLUMNAS.items():
        for i, n in enumerate(nombres):
            if i in mapa.values() or not n:
                continue
            if any(p in n for p in pistas):
                mapa[clave] = i
                break
    if "fecha" in mapa and ({"credito"} & mapa.keys() or "valor" in mapa):
        return mapa
    return None


def _filas(datos: bytes, nombre: str) -> list[list[object]]:
    if datos[:2] == b"PK":  # .xlsx (zip)
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(datos), read_only=True, data_only=True)
        return [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    if nombre.lower().endswith(".xls"):
        raise ValidacionError("El formato .xls antiguo no se puede leer: ábralo en Excel y guárdelo como .xlsx o .csv")
    for codif in ("utf-8-sig", "latin-1"):
        try:
            texto = datos.decode(codif)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialecto = csv.Sniffer().sniff(texto[:4000], delimiters=",;\t|")
        sep = dialecto.delimiter
    except csv.Error:
        sep = ";" if texto.count(";") > texto.count(",") else ","
    return [list(r) for r in csv.reader(io.StringIO(texto), delimiter=sep)]


def leer_extracto(datos: bytes, nombre: str) -> list[MovimientoBanco]:
    if len(datos) > MAX_BYTES:
        raise ValidacionError("El extracto supera 5 MB: exporte solo el mes que va a conciliar")
    filas = _filas(datos, nombre)
    for i, fila in enumerate(filas[:40]):
        mapa = _mapear(fila)
        if mapa:
            inicio = i + 1
            break
    else:
        raise ValidacionError(
            "No encontré las columnas del extracto. Debe tener al menos una columna de fecha y una de valor "
            "(o de crédito/abono). Exporte el movimiento desde la banca en línea como Excel o CSV."
        )
    salida: list[MovimientoBanco] = []
    for n, fila in enumerate(filas[inicio:], start=inicio + 1):

        def celda(clave: str, fila: list[object] = fila) -> object:
            i = mapa.get(clave)
            return fila[i] if i is not None and i < len(fila) else None

        fecha = parse_fecha(celda("fecha"))
        if fecha is None:
            continue
        if "credito" in mapa:
            valor = parse_monto(celda("credito"))
        else:
            valor = parse_monto(celda("valor"))
        if valor is None or valor <= 0:
            continue  # solo entradas de dinero
        ref = str(celda("referencia") or "").strip() or None
        salida.append(
            MovimientoBanco(
                fila=n,
                fecha=fecha,
                descripcion=" ".join(str(celda("descripcion") or "").split())[:300],
                referencia=" ".join(ref.split())[:80].upper() if ref else None,
                pagador=" ".join(str(celda("pagador") or "").split())[:200] or None,
                valor=valor.quantize(Decimal("0.01")),
            )
        )
        if len(salida) > MAX_MOVIMIENTOS:
            raise ValidacionError(f"El extracto tiene más de {MAX_MOVIMIENTOS} entradas: exporte un periodo más corto")
    return salida


def referencia_estable(m: MovimientoBanco) -> str:
    """La del banco si la trae (y no es genérica); si no, una calculada que no cambia al volver a subir el archivo."""
    if m.referencia and len(re.sub(r"\W", "", m.referencia)) >= 4 and not set(m.referencia) <= {"0"}:
        return m.referencia[:100]
    huella = hashlib.sha256(f"{m.fecha}|{m.valor}|{normalizar(m.descripcion)}".encode()).hexdigest()[:8].upper()
    return f"EXT-{m.fecha:%Y%m%d}-{int(m.valor)}-{huella}"


def medio_de(m: MovimientoBanco) -> MedioPago:
    return MedioPago.CONSIGNACION if "consig" in normalizar(m.descripcion) else MedioPago.TRANSFERENCIA


# --------------------------------------------------------------------------------------------- sugerencias
@dataclass
class UnidadCandidata:
    id: uuid.UUID
    etiqueta: str
    torre: str
    numero: str
    montos: set[Decimal] = field(default_factory=set)  # saldo total, cuota del mes, cuota con descuento
    nombres: list[tuple[set[str], bool]] = field(default_factory=list)  # (palabras del nombre, responsable)


_VACIAS = {"de", "del", "la", "las", "los", "y", "sas", "s.a.s", "ltda", "pago", "abono", "transferencia", "trf"}
_TIPO_UNIDAD = r"(?:apto|apt|ap|apartamento|casa|cs|local|lc|loc|oficina|of|ofi|unidad|und|inmueble)"


def _palabras(texto: str) -> set[str]:
    return {p for p in re.findall(r"[a-z]{3,}", normalizar(texto)) if p not in _VACIAS}


def puntuar(m: MovimientoBanco, unidades: list[UnidadCandidata]) -> tuple[UnidadCandidata | None, int, list[str]]:
    """Mejor unidad para un movimiento, con puntaje (0–100+) y motivos (función pura, probada sin base)."""
    texto = normalizar(f"{m.descripcion} {m.referencia or ''} {m.pagador or ''}")
    numeros = {}
    for u in unidades:
        numeros.setdefault(normalizar(u.numero), []).append(u)
    con_valor = [u for u in unidades if m.valor in u.montos]
    palabras = _palabras(f"{m.descripcion} {m.pagador or ''}")
    mejor: tuple[UnidadCandidata | None, int, list[str]] = (None, 0, [])
    for u in unidades:
        puntos, motivos = 0, []
        num, torre = re.escape(normalizar(u.numero)), re.escape(normalizar(u.torre))
        unico = len(numeros.get(normalizar(u.numero), [])) == 1
        if torre and re.search(
            rf"(?<![\d])(?:t(?:orre)?|bl(?:oque)?|int(?:erior)?)?\s*{torre}\s*[-/ ]?\s*{_TIPO_UNIDAD}?\.?\s*{num}(?!\d)",
            texto,
        ):
            puntos, motivos = 60, [f"La referencia menciona {u.etiqueta}"]
        elif re.search(rf"{_TIPO_UNIDAD}\.?\s*{num}(?!\d)", texto) and unico:
            puntos, motivos = 50, [f"La referencia menciona la unidad {u.numero}"]
        elif unico and len(u.numero) >= 3 and re.search(rf"(?<![\d.,]){num}(?![\d.,])", texto):
            puntos, motivos = 25, [f"La descripción contiene el número {u.numero}"]
        if m.valor in u.montos:
            if len(con_valor) == 1:
                puntos += 40
                motivos.append("El valor coincide con lo que debe solo esta unidad")
            else:
                puntos += 10
                motivos.append(f"El valor coincide con lo que deben {len(con_valor)} unidades")
        for nombre, responsable in u.nombres:
            comunes = nombre & palabras
            if len(comunes) >= 2 or (len(nombre) == 1 and comunes):
                # Nombre completo (o 3 palabras) pesa más que dos palabras sueltas
                completo = len(comunes) >= 3 or comunes == nombre
                puntos += (55 if completo else 40) + (5 if responsable else 0)
                motivos.append(
                    "El pagador coincide con "
                    + ("el responsable de pago" if responsable else "una persona de la unidad")
                )
                break
        if puntos > mejor[1]:
            mejor = (u, puntos, motivos)
    return mejor


def confianza(puntos: int) -> str:
    return "alta" if puntos >= 80 else "media" if puntos >= 50 else "baja" if puntos >= 25 else "ninguna"


async def _unidades(db: AsyncSession) -> list[UnidadCandidata]:
    filas = await db.scalars(select(Unit).where(Unit.activa, Unit.unidad_principal_id.is_(None)))
    unidades = {u.id: UnidadCandidata(u.id, u.etiqueta, u.tower or "", u.number) for u in filas}
    # Saldo total vigente
    for uid, saldo in (
        await db.execute(
            select(SaldoCargo.unidad_id, func.sum(SaldoCargo.saldo))
            .where(SaldoCargo.estado == EstadoCargo.VIGENTE, SaldoCargo.saldo > 0)
            .group_by(SaldoCargo.unidad_id)
        )
    ).all():
        if uid in unidades:
            unidades[uid].montos.add(Decimal(saldo).quantize(Decimal("0.01")))
    # Cuota del último periodo (y con el descuento por pronto pago)
    ultimo = await db.scalar(
        select(PeriodoCartera.id).order_by(PeriodoCartera.anio.desc(), PeriodoCartera.mes.desc()).limit(1)
    )
    if ultimo:
        cuotas: dict[uuid.UUID, tuple[Decimal, Decimal]] = {}
        for c in await db.scalars(select(CargoCartera).where(CargoCartera.periodo_id == ultimo)):
            total, desc = cuotas.get(c.unidad_id, (Decimal(0), Decimal(0)))
            pct = (c.descuento_pct or Decimal(0)) / 100
            cuotas[c.unidad_id] = (total + c.valor, desc + c.valor * (1 - pct))
        for uid, (total, desc) in cuotas.items():
            if uid in unidades:
                unidades[uid].montos |= {
                    total.quantize(Decimal("0.01")),
                    desc.quantize(Decimal("1")).quantize(Decimal("0.01")),
                }
    # Personas vigentes
    for uid, nombre, responsable in (
        await db.execute(
            select(UnidadPersona.unidad_id, Persona.nombre_completo, UnidadPersona.responsable_pago)
            .join(Persona, Persona.id == UnidadPersona.persona_id)
            .where(UnidadPersona.fecha_fin.is_(None))
        )
    ).all():
        if uid in unidades:
            unidades[uid].nombres.append((_palabras(nombre), bool(responsable)))
    return sorted(unidades.values(), key=lambda u: u.etiqueta)


async def sugerir(db: AsyncSession, actor: Actor, movimientos: list[MovimientoBanco]) -> dict[str, object]:
    exigir(actor, PUEDE_REGISTRAR_PAGO, "conciliar pagos de cartera")
    unidades = await _unidades(db)
    refs = [referencia_estable(m) for m in movimientos]
    existentes = {
        p.referencia: p
        for p in await db.scalars(
            select(PagoCartera).where(
                PagoCartera.referencia.in_(refs), PagoCartera.estado == EstadoPagoCartera.APLICADO
            )
        )
    }
    desde = min((m.fecha for m in movimientos), default=date.today()) - timedelta(days=1)
    por_fecha_valor = {
        (p.fecha_pago, p.valor, p.unidad_id): p
        for p in await db.scalars(
            select(PagoCartera).where(PagoCartera.fecha_pago >= desde, PagoCartera.estado == EstadoPagoCartera.APLICADO)
        )
    }
    salida = []
    for m, ref in zip(movimientos, refs, strict=True):
        u, puntos, motivos = puntuar(m, unidades)
        nivel = confianza(puntos)
        previo = existentes.get(ref) or (u and por_fecha_valor.get((m.fecha, m.valor, u.id)))
        salida.append(
            {
                "fila": m.fila,
                "fecha": m.fecha,
                "descripcion": m.descripcion,
                "pagador": m.pagador,
                "valor": m.valor,
                "referencia": ref,
                "medio_pago": medio_de(m),
                "unidad_id": u.id if u and nivel != "ninguna" else None,
                "unidad": u.etiqueta if u and nivel != "ninguna" else None,
                "confianza": nivel,
                "motivos": motivos if nivel != "ninguna" else [],
                "ya_registrado": f"Recibo {previo.consecutivo}" if previo else None,
            }
        )
    return {"movimientos": salida, "unidades": [{"id": u.id, "etiqueta": u.etiqueta} for u in unidades]}


async def registrar(db: AsyncSession, actor: Actor, items: list[PagoIn], filas: list[int]) -> dict[str, object]:
    """Registra cada pago en su propio punto de guardado: uno con error no impide los demás."""
    exigir(actor, PUEDE_REGISTRAR_PAGO, "registrar pagos de cartera")
    creados, errores = [], []
    for fila, item in zip(filas, items, strict=True):
        try:
            async with db.begin_nested():
                r = await pagos.registrar_pago(db, actor, item)
                await db.refresh(r.pago)  # el consecutivo del recibo lo asigna la base
            creados.append({"fila": fila, "pago_id": r.pago.id, "recibo": r.pago.consecutivo, "valor": item.valor})
        except (ValidacionError, NoEncontrado) as e:
            errores.append({"fila": fila, "motivo": str(e)})
    return {"creados": creados, "errores": errores}
