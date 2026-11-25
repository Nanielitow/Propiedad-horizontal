"""Dibuja un `Reporte` en JSON (pantalla), Excel (.xlsx) y PDF.

Excel: una hoja de resumen y una hoja por tabla, con montos como NÚMEROS en
formato de pesos (se pueden sumar y filtrar), encabezados fijos y totales.
PDF: HTML + CSS maquetado con PyMuPDF (Story), con encabezado y numeración.
"""

import io
from datetime import date, datetime
from decimal import Decimal
from html import escape
from typing import Any

import pymupdf
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.services.recaudos.dominio import TZ, pesos
from app.services.recaudos.reportes import Columna, Reporte, Tabla

AZUL = "1F3A5F"
GRIS = "F2F4F7"
FORMATO_DINERO = '"$"#,##0;-"$"#,##0'


def _local(v: datetime) -> datetime:
    return v.astimezone(TZ)


def texto_celda(valor: Any, col: Columna) -> str:
    """Valor formateado para leer (pantalla y PDF)."""
    if valor is None or valor == "":
        return ""
    if col.tipo == "dinero":
        return pesos(Decimal(str(valor)))
    if col.tipo == "porcentaje":
        return f"{Decimal(str(valor)):.1f} %".replace(".", ",")
    if col.tipo == "coeficiente":  # coeficiente de copropiedad: 4 decimales
        return f"{Decimal(str(valor)):.4f}".replace(".", ",")
    if col.tipo == "entero" and isinstance(valor, int):
        return f"{valor:,}".replace(",", ".")
    if isinstance(valor, datetime):
        local = _local(valor)
        return local.strftime("%d/%m/%Y %H:%M") if col.tipo == "fechahora" else local.strftime("%d/%m/%Y")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    return str(valor)


# --- JSON ---------------------------------------------------------------------------------


def _json(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, datetime):
        return _local(valor).isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    return valor


def a_json(r: Reporte) -> dict[str, Any]:
    return {
        "tipo": r.tipo,
        "titulo": r.titulo,
        "copropiedad": r.copropiedad,
        "periodo": r.periodo,
        "desde": r.desde.isoformat(),
        "hasta": r.hasta.isoformat(),
        "generado": r.generado.isoformat(),
        "resumen": [{"etiqueta": k, "valor": v} for k, v in r.resumen],
        "tablas": [
            {
                "titulo": t.titulo,
                "columnas": [{"titulo": c.titulo, "tipo": c.tipo} for c in t.columnas],
                "filas": [[_json(v) for v in fila] for fila in t.filas],
                "totales": [_json(v) for v in t.totales] if t.totales else None,
                "nota": t.nota,
            }
            for t in r.tablas
        ],
    }


# --- Excel --------------------------------------------------------------------------------


def _valor_excel(valor: Any, col: Columna) -> Any:
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return float(valor) / 100 if col.tipo == "porcentaje" else float(valor)
    if isinstance(valor, datetime):
        return _local(valor).replace(tzinfo=None)  # Excel no maneja zonas horarias
    return valor


def _nombre_hoja(titulo: str, usados: set[str]) -> str:
    base = "".join(ch for ch in titulo if ch not in "[]:*?/\\")[:31]
    nombre, n = base, 2
    while nombre.lower() in usados:
        nombre = f"{base[:28]} {n}"
        n += 1
    usados.add(nombre.lower())
    return nombre


def _hoja_tabla(wb: Workbook, t: Tabla, r: Reporte, usados: set[str]) -> None:
    ws = wb.create_sheet(_nombre_hoja(t.titulo, usados))
    ws["A1"] = t.titulo
    ws["A1"].font = Font(bold=True, size=13, color=AZUL)
    ws["A2"] = f"{r.copropiedad} · {r.periodo}"
    ws["A2"].font = Font(color="667085")
    fila0 = 4
    borde = Border(bottom=Side(style="thin", color="D0D5DD"))
    for j, col in enumerate(t.columnas, start=1):
        c = ws.cell(row=fila0, column=j, value=col.titulo)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=AZUL)
        c.alignment = Alignment(
            horizontal="right" if col.tipo in ("dinero", "entero", "porcentaje", "coeficiente") else "left",
            vertical="center",
        )
    for i, fila in enumerate(t.filas, start=fila0 + 1):
        for j, (valor, col) in enumerate(zip(fila, t.columnas, strict=True), start=1):
            c = ws.cell(row=i, column=j, value=_valor_excel(valor, col))
            c.border = borde
            if col.tipo == "dinero":
                c.number_format = FORMATO_DINERO
            elif col.tipo == "porcentaje":
                c.number_format = "0.0%"
            elif col.tipo == "coeficiente":
                c.number_format = "0.0000"
            elif col.tipo == "fechahora":
                c.number_format = "dd/mm/yyyy hh:mm"
            elif col.tipo == "fecha":
                c.number_format = "dd/mm/yyyy"
    ultima = fila0 + len(t.filas)
    if t.totales:
        ultima += 1
        for j, (valor, col) in enumerate(zip(t.totales, t.columnas, strict=True), start=1):
            c = ws.cell(row=ultima, column=j, value=_valor_excel(valor, col))
            c.font = Font(bold=True)
            c.fill = PatternFill("solid", fgColor=GRIS)
            if col.tipo == "dinero":
                c.number_format = FORMATO_DINERO
            elif col.tipo == "porcentaje":
                c.number_format = "0.0%"
            elif col.tipo == "coeficiente":
                c.number_format = "0.0000"
    if t.nota:
        ws.cell(row=ultima + 2, column=1, value=t.nota).font = Font(italic=True, color="667085")
    ws.freeze_panes = ws.cell(row=fila0 + 1, column=1)
    if t.filas:
        ws.auto_filter.ref = f"A{fila0}:{get_column_letter(len(t.columnas))}{fila0 + len(t.filas)}"
    for j, col in enumerate(t.columnas, start=1):
        largo = max([len(col.titulo)] + [len(texto_celda(f[j - 1], col)) for f in t.filas[:500]])
        ws.column_dimensions[get_column_letter(j)].width = min(max(largo + 3, 10), 60)


def a_excel(r: Reporte) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Resumen"
    ws["A1"] = r.titulo
    ws["A1"].font = Font(bold=True, size=15, color=AZUL)
    ws["A2"] = r.copropiedad
    ws["A3"] = f"Periodo: {r.periodo}"
    ws["A4"] = f"Generado: {r.generado.strftime('%d/%m/%Y %H:%M')} · PH Gestión"
    for celda in ("A2", "A3", "A4"):
        ws[celda].font = Font(color="667085")
    for i, (k, v) in enumerate(r.resumen, start=6):
        ws.cell(row=i, column=1, value=k).font = Font(color="475467")
        ws.cell(row=i, column=2, value=v).font = Font(bold=True)
    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 34
    usados = {"resumen"}
    for t in r.tablas:
        _hoja_tabla(wb, t, r, usados)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# --- PDF ---------------------------------------------------------------------------------

_CSS = """
* { font-family: sans-serif; }
body { font-size: 8.5pt; color: #1b2430; }
h1 { font-size: 15pt; color: #1f3a5f; margin: 0 0 2pt 0; }
h2 { font-size: 10.5pt; color: #1f3a5f; margin: 12pt 0 4pt 0; }
p.sub { color: #667085; margin: 0 0 8pt 0; }
p.nota { color: #667085; font-style: italic; font-size: 7.5pt; margin: 3pt 0 0 0; }
table { border-collapse: collapse; width: 100%; }
th { background-color: #1f3a5f; color: #ffffff; text-align: left; padding: 3pt 4pt; font-size: 7.5pt; }
td { padding: 2.5pt 4pt; border-bottom: 0.5pt solid #d0d5dd; font-size: 7.5pt; }
td.num, th.num { text-align: right; }
tr.total td { font-weight: bold; background-color: #f2f4f7; }
p.kv { font-size: 9pt; color: #475467; margin: 0 0 2pt 0; }
p.kv b { color: #1b2430; }
"""


def _html(r: Reporte) -> str:
    partes = [
        f"<h1>{escape(r.titulo)}</h1>",
        f"<p class='sub'>{escape(r.copropiedad)} · {escape(r.periodo)} · generado el {r.generado.strftime('%d/%m/%Y %H:%M')}</p>",
        # Resumen como líneas (el maquetador de PyMuPDF no respeta anchos en tablas de dos columnas)
        *[f"<p class='kv'>{escape(k)}: <b>{escape(v)}</b></p>" for k, v in r.resumen],
    ]
    for t in r.tablas:
        numericas = {i for i, c in enumerate(t.columnas) if c.tipo in ("dinero", "entero", "porcentaje", "coeficiente")}

        def celda(i: int, contenido: str, tag: str = "td", numericas: set[int] = numericas) -> str:
            clase = " class='num'" if i in numericas else ""
            return f"<{tag}{clase}>{escape(contenido)}</{tag}>"

        partes.append(f"<h2>{escape(t.titulo)}</h2>")
        if not t.filas:
            partes.append("<p class='nota'>Sin registros en el periodo.</p>")
            continue
        partes.append("<table><tr>" + "".join(celda(i, c.titulo, "th") for i, c in enumerate(t.columnas)) + "</tr>")
        for fila in t.filas:
            partes.append(
                "<tr>"
                + "".join(celda(i, texto_celda(v, c)) for i, (v, c) in enumerate(zip(fila, t.columnas, strict=True)))
                + "</tr>"
            )
        if t.totales:
            partes.append(
                "<tr class='total'>"
                + "".join(
                    celda(i, texto_celda(v, c)) for i, (v, c) in enumerate(zip(t.totales, t.columnas, strict=True))
                )
                + "</tr>"
            )
        partes.append("</table>")
        if t.nota:
            partes.append(f"<p class='nota'>{escape(t.nota)}</p>")
    return "".join(partes)


def a_pdf(r: Reporte) -> bytes:
    # Horizontal cuando alguna tabla es ancha (detalle de parqueadero, auditoría)
    ancho = max((len(t.columnas) for t in r.tablas), default=0) >= 7
    pagina = pymupdf.paper_rect("a4-l" if ancho else "a4")
    area = pagina + (36, 48, -36, -40)
    story = pymupdf.Story(html=_html(r), user_css=_CSS)
    buffer = io.BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    mas = 1
    while mas:
        dispositivo = writer.begin_page(pagina)
        mas, _ = story.place(area)
        story.draw(dispositivo)
        writer.end_page()
    writer.close()

    # Encabezado y pie con numeración (se conoce el total de páginas al final)
    doc = pymupdf.open("pdf", buffer.getvalue())
    total = doc.page_count
    for i, page in enumerate(doc, start=1):
        page.insert_text((36, 28), f"PH Gestión · {r.copropiedad}", fontsize=7.5, color=(0.4, 0.44, 0.52))
        titulo = r.titulo if r.tipo == "corte" else f"{r.titulo} · {r.periodo}"  # el corte ya trae el mes en el título
        pie = f"{titulo} · Página {i} de {total}"
        page.insert_text((36, pagina.height - 20), pie, fontsize=7.5, color=(0.4, 0.44, 0.52))
    doc.set_metadata({"title": r.titulo, "author": "PH Gestión", "subject": f"{r.copropiedad} · {r.periodo}"})
    salida = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return salida
