"""Documentos de la cartera: estado de cuenta y morosos (motor de reportes compartido) y
documentos de una página (paz y salvo, recibo de pago) maquetados con PyMuPDF."""

import io
from datetime import date, datetime
from decimal import Decimal
from html import escape

import pymupdf

from app.schemas.cartera_out import EstadoCuenta, MorososOut, PagoOut
from app.services.activos.reportes import ReporteActivos
from app.services.cartera.dominio import MESES
from app.services.comun import TZ, pesos
from app.services.recaudos.reportes import Columna, Tabla

RANGOS = {
    "corriente": "Sin vencer",
    "1_30": "1 a 30 días",
    "31_60": "31 a 60 días",
    "61_90": "61 a 90 días",
    "mas_90": "Más de 90 días",
}
MEDIO = {"EFECTIVO": "Efectivo", "TRANSFERENCIA": "Transferencia", "CONSIGNACION": "Consignación"}


def reporte_estado_cuenta(e: EstadoCuenta) -> ReporteActivos:
    resumen = [
        ("Unidad", e.unidad),
        ("Responsable", e.responsable or "—"),
        ("Saldo total", pesos(e.saldo_total)),
        ("Saldo vencido", pesos(e.saldo_vencido)),
        ("Saldo a favor", pesos(e.saldo_a_favor)),
        ("Estado", "Al día" if e.al_dia else f"En mora ({e.dias_mora} días)"),
    ]
    pendientes = Tabla(
        "Cargos pendientes",
        [
            Columna("Concepto"),
            Columna("Vence", "fecha"),
            Columna("Valor", "dinero"),
            Columna("Saldo", "dinero"),
            Columna("Días de mora", "entero"),
        ],
        [[c.descripcion, c.fecha_vencimiento, c.valor, c.saldo, c.dias_mora] for c in e.pendientes],
        totales=["Total", None, None, e.saldo_total, None],
    )
    movimientos = Tabla(
        "Movimientos",
        [
            Columna("Fecha", "fecha"),
            Columna("Detalle"),
            Columna("Cargo", "dinero"),
            Columna("Abono", "dinero"),
            Columna("Saldo", "dinero"),
        ],
        [
            [m.fecha, m.descripcion + (" (ANULADO)" if m.anulado else ""), m.cargo or None, m.abono or None, m.saldo]
            for m in e.movimientos
        ],
        nota="Los pagos se imputan primero a intereses y luego a la deuda más antigua (art. 1653 del Código Civil).",
    )
    return ReporteActivos(
        tipo="estado-cuenta",
        titulo=f"Estado de cuenta {e.unidad}",
        copropiedad=e.copropiedad,
        desde=e.corte,
        hasta=e.corte,
        generado=datetime.now(TZ),
        resumen=resumen,
        tablas=[pendientes, movimientos],
        corte=True,
    )


def reporte_morosos(m: MorososOut, copropiedad: str) -> ReporteActivos:
    cols = [Columna("Unidad"), Columna("Responsable"), Columna("Vencido", "dinero")]
    cols += [Columna(RANGOS[k], "dinero") for k in ("1_30", "31_60", "61_90", "mas_90")]
    cols += [Columna("Días", "entero"), Columna("Último pago", "fecha")]
    filas = [
        [
            x.unidad,
            x.responsable or "",
            x.saldo_vencido,
            *(x.edades[k] or None for k in ("1_30", "31_60", "61_90", "mas_90")),
            x.dias_mora,
            x.ultimo_pago,
        ]
        for x in m.items
    ]
    totales = ["Total", "", m.total_vencido, *(m.edades[k] for k in ("1_30", "31_60", "61_90", "mas_90")), None, None]
    return ReporteActivos(
        tipo="morosos",
        titulo="Cartera morosa por antigüedad",
        copropiedad=copropiedad,
        desde=m.corte,
        hasta=m.corte,
        generado=datetime.now(TZ),
        resumen=[("Unidades en mora", str(len(m.items))), ("Total vencido", pesos(m.total_vencido))],
        tablas=[
            Tabla(
                "Unidades en mora",
                cols,
                filas,
                totales,
                nota="Uso interno: la Corte Constitucional prohíbe publicar listas de morosos en áreas comunes.",
            )
        ],
        corte=True,
    )


# --- Documentos de una página ------------------------------------------------------------------

_CSS = """
* { font-family: sans-serif; }
body { font-size: 10pt; color: #1b2430; }
h1 { font-size: 18pt; color: #1f3a5f; margin: 0 0 4pt 0; text-align: center; }
p.sub { color: #667085; text-align: center; margin: 0 0 18pt 0; }
p { margin: 0 0 8pt 0; line-height: 1.45; }
p.kv { margin: 0 0 3pt 0; color: #475467; }
p.kv b { color: #1b2430; }
p.firma { margin-top: 36pt; color: #475467; }
p.codigo { margin-top: 18pt; padding: 6pt; background-color: #f2f4f7; text-align: center; font-size: 11pt; }
p.pie { margin-top: 14pt; color: #667085; font-size: 8pt; }
"""


def _pdf(html: str, titulo: str, copropiedad: str) -> bytes:
    pagina = pymupdf.paper_rect("letter")
    story = pymupdf.Story(html=html, user_css=_CSS)
    buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    mas = 1
    while mas:
        dev = writer.begin_page(pagina)
        mas, _ = story.place(pagina + (60, 60, -60, -60))
        story.draw(dev)
        writer.end_page()
    writer.close()
    doc = pymupdf.open("pdf", buf.getvalue())
    for page in doc:
        page.insert_text((60, 36), f"PH Gestión · {copropiedad}", fontsize=8, color=(0.4, 0.44, 0.52))
    doc.set_metadata({"title": titulo, "author": "PH Gestión", "subject": copropiedad})
    salida = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return salida


def _fecha_larga(f: date) -> str:
    return f"{f.day} de {MESES[f.month - 1]} de {f.year}"


def paz_y_salvo_pdf(
    *,
    copropiedad: str,
    nit: str | None,
    unidad: str,
    titular: str | None,
    consecutivo: int,
    emision: date,
    valido_hasta: date,
    codigo: str,
) -> bytes:
    nit_txt = f", NIT {escape(nit)}" if nit else ""
    html = f"""
    <h1>Paz y salvo</h1>
    <p class='sub'>N.º {consecutivo:05d}</p>
    <p>La administración de <b>{escape(copropiedad)}</b>{nit_txt} certifica que la unidad
    <b>{escape(unidad)}</b>{f", a nombre de <b>{escape(titular)}</b>," if titular else ""} se encuentra
    <b>a paz y salvo</b> por concepto de cuotas de administración, cuotas extraordinarias, intereses de mora
    y demás obligaciones económicas con la copropiedad, causadas y vencidas a la fecha de expedición.</p>
    <p>Se expide el {_fecha_larga(emision)} y es válido hasta el {_fecha_larga(valido_hasta)}.</p>
    <p class='firma'>Administración<br/>{escape(copropiedad)}</p>
    <p class='codigo'>Código de verificación: <b>{escape(codigo)}</b></p>
    <p class='pie'>Para verificar la autenticidad de este documento, comuníquese con la administración e indique el
    código de verificación. Documento generado electrónicamente por PH Gestión.</p>
    """
    return _pdf(html, f"Paz y salvo {unidad}", copropiedad)


def recibo_pdf(
    *, copropiedad: str, nit: str | None, p: PagoOut, aplicaciones: list[tuple[str, Decimal, Decimal]], saldo: Decimal
) -> bytes:
    filas = "".join(
        f"<p class='kv'>{escape(desc)}: <b>{pesos(v)}</b>{f' (descuento {pesos(dto)})' if dto else ''}</p>"
        for desc, v, dto in aplicaciones
    )
    anulado = "<p><b>RECIBO ANULADO</b>: " + escape(p.motivo_anulacion or "") + "</p>" if p.estado == "ANULADO" else ""
    html = f"""
    <h1>Recibo de caja</h1>
    <p class='sub'>N.º {p.consecutivo:06d}{f" · NIT {escape(nit)}" if nit else ""}</p>
    {anulado}
    <p class='kv'>Copropiedad: <b>{escape(copropiedad)}</b></p>
    <p class='kv'>Unidad: <b>{escape(p.unidad)}</b></p>
    <p class='kv'>Fecha del pago: <b>{p.fecha_pago:%d/%m/%Y}</b></p>
    <p class='kv'>Valor recibido: <b>{pesos(p.valor)}</b></p>
    <p class='kv'>Medio: <b>{MEDIO.get(p.medio_pago.value, p.medio_pago.value)}</b>{f" · referencia {escape(p.referencia)}" if p.referencia else ""}</p>
    {f"<p class='kv'>Pagó: <b>{escape(p.pagador_nombre)}</b></p>" if p.pagador_nombre else ""}
    <p style='margin-top:12pt'><b>Aplicado a</b></p>
    {filas or "<p class='kv'>Quedó como saldo a favor.</p>"}
    {f"<p class='kv'>Saldo a favor: <b>{pesos(p.a_favor)}</b></p>" if p.a_favor else ""}
    <p class='kv' style='margin-top:10pt'>Saldo pendiente de la unidad después de este pago: <b>{pesos(saldo)}</b></p>
    <p class='pie'>Registrado por {escape(p.registrado_por or "la administración")} el {p.created_at.astimezone(TZ):%d/%m/%Y %H:%M}.
    Documento generado electrónicamente por PH Gestión.</p>
    """
    return _pdf(html, f"Recibo {p.consecutivo}", copropiedad)
