"""Códigos QR de los activos y hoja de etiquetas imprimibles.

El QR solo contiene un ENLACE con un token aleatorio: quien lo escanea debe
iniciar sesión y ve lo que su rol permite. Una etiqueta fotografiada no expone
datos, y si se pierde se regenera el token (el QR anterior deja de funcionar).
"""

import io

import pymupdf
import segno

from app.core.config import get_settings
from app.models import Activo

# Etiquetas: 2 columnas x 5 filas en A4 (cada una ~9 x 5 cm, fácil de pegar en un equipo)
COLUMNAS, FILAS = 2, 5
MARGEN = 28  # puntos (~1 cm)


def url_qr(tenant_slug: str, token: str) -> str:
    return f"{get_settings().app_url.rstrip('/')}/{tenant_slug}/activos/qr/{token}"


def svg(url: str, *, escala: int = 6) -> str:
    """SVG sin dependencias de navegador; corrección de errores media (resiste rayones)."""
    qr = segno.make(url, error="m")
    buffer = io.BytesIO()
    qr.save(buffer, kind="svg", scale=escala, border=2, xmldecl=False, dark="#1b2430")
    return buffer.getvalue().decode()


def png(url: str, *, escala: int = 10) -> bytes:
    buffer = io.BytesIO()
    segno.make(url, error="m").save(buffer, kind="png", scale=escala, border=2)
    return buffer.getvalue()


def _recortar(texto: str, maximo: int) -> str:
    return texto if len(texto) <= maximo else texto[: maximo - 1] + "…"


def etiquetas_pdf(activos: list[Activo], tenant_slug: str, copropiedad: str) -> bytes:
    """Hoja A4 con una etiqueta por activo: QR, código, nombre, ubicación e instrucción."""
    doc = pymupdf.open()
    pagina_rect = pymupdf.paper_rect("a4")
    ancho = (pagina_rect.width - 2 * MARGEN) / COLUMNAS
    alto = (pagina_rect.height - 2 * MARGEN) / FILAS
    gris = (0.4, 0.44, 0.52)
    azul = (0.12, 0.23, 0.37)
    pagina = None
    for i, a in enumerate(activos):
        if i % (COLUMNAS * FILAS) == 0:
            pagina = doc.new_page(width=pagina_rect.width, height=pagina_rect.height)
        assert pagina is not None
        pos = i % (COLUMNAS * FILAS)
        x0 = MARGEN + (pos % COLUMNAS) * ancho
        y0 = MARGEN + (pos // COLUMNAS) * alto
        caja = pymupdf.Rect(x0 + 6, y0 + 6, x0 + ancho - 6, y0 + alto - 6)
        pagina.draw_rect(caja, color=(0.82, 0.84, 0.87), width=0.6, dashes="[3 2] 0")  # línea de corte
        lado = caja.height - 16
        qr_rect = pymupdf.Rect(caja.x0 + 8, caja.y0 + 8, caja.x0 + 8 + lado, caja.y0 + 8 + lado)
        pagina.insert_image(qr_rect, stream=png(url_qr(tenant_slug, a.qr_token)))
        tx = qr_rect.x1 + 10
        ancho_texto = caja.x1 - tx - 8
        chars = max(12, int(ancho_texto / 5.2))
        pagina.insert_text((tx, caja.y0 + 26), a.codigo_interno, fontsize=16, fontname="hebo", color=azul)
        pagina.insert_text((tx, caja.y0 + 44), _recortar(a.nombre, chars), fontsize=10, fontname="hebo")
        pagina.insert_text((tx, caja.y0 + 58), _recortar(a.ubicacion, chars + 4), fontsize=8.5, color=gris)
        pagina.insert_text((tx, caja.y1 - 22), "Escanee con la cámara del celular", fontsize=7.5, color=gris)
        pagina.insert_text(
            (tx, caja.y1 - 12), _recortar(f"PH Gestión · {copropiedad}", chars + 6), fontsize=7.5, color=gris
        )
    if pagina is None:
        doc.new_page(width=pagina_rect.width, height=pagina_rect.height)
    doc.set_metadata({"title": f"Etiquetas QR · {copropiedad}", "author": "PH Gestión"})
    salida = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return salida
