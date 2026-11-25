"""Acta de la asamblea: borrador en PDF con instalación, quórum, asistencia, poderes y el
resultado de cada votación, listo para que el secretario lo complete y lo firmen.

Guardarla la convierte en un documento de la categoría Actas: entra al buscador con IA y
al resumidor de actas (acuerdos y tareas), como cualquier PDF subido.
"""

import hashlib
import io
import uuid
from decimal import Decimal
from html import escape

import pymupdf
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asamblea, AsistenciaAsamblea, Document, PadronAsamblea, PuntoAsamblea, Tenant
from app.models.enums import (
    AccessLevel,
    DocumentCategory,
    DocumentStatus,
    EstadoAsamblea,
    MayoriaPunto,
    TipoAsistente,
    TipoPunto,
)
from app.services.asambleas import dominio as d
from app.services.comun import TZ, Actor, ValidacionError, exigir
from app.services.storage.s3 import get_storage

MESES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]
MAYORIA = {
    MayoriaPunto.SIMPLE: "mayoría simple (mitad más uno de los coeficientes presentes)",
    MayoriaPunto.CALIFICADA_70: "mayoría calificada (70 % de los coeficientes del conjunto, art. 46 Ley 675)",
    MayoriaPunto.ELECCION: "elección (gana la opción con más coeficiente)",
}

_CSS = """
* { font-family: sans-serif; }
body { font-size: 9.5pt; color: #1b2430; }
h1 { font-size: 15pt; color: #1f3a5f; text-align: center; margin: 0 0 2pt 0; }
p.sub { text-align: center; color: #667085; margin: 0 0 12pt 0; }
h2 { font-size: 11pt; color: #1f3a5f; margin: 12pt 0 4pt 0; }
p { margin: 0 0 6pt 0; line-height: 1.4; }
table { border-collapse: collapse; width: 100%; margin: 2pt 0 6pt 0; }
th { background-color: #1f3a5f; color: #ffffff; text-align: left; padding: 2pt 4pt; font-size: 8pt; }
td { padding: 2pt 4pt; border-bottom: 0.5pt solid #d0d5dd; font-size: 8pt; }
td.num, th.num { text-align: right; }
p.firma { margin-top: 30pt; }
"""


def _pct(v: Decimal, total: Decimal) -> str:
    return f"{(v / total * 100):.2f}".replace(".", ",") if total else "0,00"


def _fecha(dt: object) -> str:
    local = dt.astimezone(TZ)  # type: ignore[attr-defined]
    return f"{local.day} de {MESES[local.month - 1]} de {local.year}"


async def generar_pdf(db: AsyncSession, a: Asamblea) -> bytes:
    if a.estado != EstadoAsamblea.CERRADA:
        raise ValidacionError("El acta se genera cuando la asamblea está cerrada")
    tenant = await db.get(Tenant, a.tenant_id)
    padron = {
        p.unidad_id: p for p in await db.scalars(select(PadronAsamblea).where(PadronAsamblea.asamblea_id == a.id))
    }
    asistencias = list(
        await db.scalars(
            select(AsistenciaAsamblea)
            .where(AsistenciaAsamblea.asamblea_id == a.id)
            .order_by(AsistenciaAsamblea.llegada_at)
        )
    )
    puntos = list(
        await db.scalars(select(PuntoAsamblea).where(PuntoAsamblea.asamblea_id == a.id).order_by(PuntoAsamblea.orden))
    )
    total = a.coeficiente_total or Decimal(0)
    unicas = {x.unidad_id: x for x in asistencias}  # una unidad cuenta una vez aunque haya salido y vuelto
    presente_max = sum((padron[u].coeficiente for u in unicas if u in padron), Decimal(0))
    apoderados = [x for x in unicas.values() if x.tipo == TipoAsistente.APODERADO]
    virtuales = sum(1 for x in unicas.values() if x.virtual)
    inicio = a.abierta_at.astimezone(TZ) if a.abierta_at else None
    fin = a.cerrada_at.astimezone(TZ) if a.cerrada_at else None
    copropiedad = tenant.name if tenant else ""
    q = d.Quorum(presente_max, total, len(unicas), len(padron), a.convocatoria)

    partes = [
        f"<h1>Acta N.º {a.consecutivo:03d} · Asamblea general {a.tipo.value.lower()}</h1>",
        f"<p class='sub'>{escape(copropiedad)}{f' · NIT {escape(tenant.nit)}' if tenant and tenant.nit else ''}</p>",
        f"<p>El {_fecha(a.abierta_at or a.fecha_hora)}{f', a las {inicio:%I:%M %p}' if inicio else ''}, "
        f"en {escape(a.lugar or 'la sede de la copropiedad')}, ",
        f"se reunió la asamblea general {a.tipo.value.lower()} de copropietarios, en reunión "
        f"{a.modalidad.value.lower()} de {'primera' if a.convocatoria.value == 'PRIMERA' else 'segunda'} convocatoria"
        f"{' (art. 41 Ley 675: decide con cualquier número plural de propietarios)' if a.convocatoria.value == 'SEGUNDA' else ''}.</p>",
        "<h2>Instalación y quórum</h2>",
        f"<p>Asistieron {len(unicas)} de {len(padron)} unidades, que representan el <b>{_pct(presente_max, total)} %</b> de los "
        f"coeficientes de copropiedad ({len(apoderados)} por medio de apoderado{'s' if len(apoderados) != 1 else ''}"
        f"{f'; {virtuales} de forma virtual' if virtuales else ''}). {escape(q.mensaje)}.</p>",
        f"<p>Presidente de la asamblea: <b>{escape(a.presidente or '')}</b>. Secretario: <b>{escape(a.secretario or '')}</b>.</p>",
        "<h2>Orden del día</h2>",
        "<p>" + "<br/>".join(f"{p.orden}. {escape(p.titulo)}" for p in puntos) + "</p>",
        "<h2>Desarrollo</h2>",
    ]
    for p in puntos:
        partes.append(f"<p><b>{p.orden}. {escape(p.titulo)}</b></p>")
        if p.descripcion:
            partes.append(f"<p>{escape(p.descripcion)}</p>")
        if p.tipo == TipoPunto.VOTACION and p.resultado:
            r = p.resultado
            partes.append(
                f"<p>Se sometió a votación por {MAYORIA.get(p.mayoria, '') if p.mayoria else ''}. Coeficiente presente: {_pct(Decimal(r['presente']), total)} %.</p>"
            )
            filas = "".join(
                f"<tr><td>{escape(o)}</td><td class='num'>{r['unidades_por_opcion'].get(o, 0)}</td>"
                f"<td class='num'>{_pct(Decimal(r['por_opcion'].get(o, 0)), total)} %</td></tr>"
                for o in p.opciones  # el JSONB no conserva el orden de las claves: se usa el del punto
            )
            partes.append(
                f"<table><tr><th>Opción</th><th class='num'>Unidades</th><th class='num'>% del conjunto</th></tr>{filas}</table>"
            )
        if p.conclusion:
            partes.append(f"<p><i>{escape(p.conclusion)}</i></p>")
    if a.observaciones:
        partes += ["<h2>Observaciones</h2>", f"<p>{escape(a.observaciones)}</p>"]
    # «p. m.» ya termina en punto: no se agrega otro
    partes.append(f"<p>Agotado el orden del día, se levantó la sesión{f' a las {fin:%I:%M %p}' if fin else '.'}</p>")
    partes.append("<h2>Asistencia</h2>")
    filas = "".join(
        f"<tr><td>{escape(padron[x.unidad_id].etiqueta)}</td><td>{escape(x.asistente_nombre)}</td>"
        f"<td>{'Apoderado' if x.tipo == TipoAsistente.APODERADO else 'Propietario'}{' (virtual)' if x.virtual else ''}</td>"
        f"<td class='num'>{_pct(padron[x.unidad_id].coeficiente, total)} %</td></tr>"
        for x in sorted(unicas.values(), key=lambda x: padron[x.unidad_id].etiqueta)
        if x.unidad_id in padron
    )
    partes.append(
        f"<table><tr><th>Unidad</th><th>Asistente</th><th>Calidad</th><th class='num'>Coeficiente</th></tr>{filas}</table>"
    )
    partes.append(
        f"<p class='firma'>______________________________<br/>{escape(a.presidente or '')}<br/>Presidente</p>"
        f"<p class='firma'>______________________________<br/>{escape(a.secretario or '')}<br/>Secretario</p>"
    )
    html = "".join(x.replace(" AM", " a. m.").replace(" PM", " p. m.") for x in partes)

    pagina = pymupdf.paper_rect("letter")
    story = pymupdf.Story(html=html, user_css=_CSS)
    buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    mas = 1
    while mas:
        dev = writer.begin_page(pagina)
        mas, _ = story.place(pagina + (54, 54, -54, -54))
        story.draw(dev)
        writer.end_page()
    writer.close()
    doc = pymupdf.open("pdf", buf.getvalue())
    n = doc.page_count
    for i, page in enumerate(doc, start=1):
        page.insert_text(
            (54, pagina.height - 28),
            f"Acta N.º {a.consecutivo:03d} · {copropiedad} · Página {i} de {n}",
            fontsize=7.5,
            color=(0.4, 0.44, 0.52),
        )
    doc.set_metadata(
        {"title": f"Acta {a.consecutivo:03d} - {a.titulo}", "author": "PH Gestión", "subject": copropiedad}
    )
    salida = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return salida


async def guardar_en_documentos(db: AsyncSession, actor: Actor, a: Asamblea, pdf: bytes) -> Document:
    """Crea el documento (categoría Actas, visible para los copropietarios) y lo enlaza a la asamblea.
    Quien llama hace commit y encola la ingesta."""
    exigir(actor, d.PUEDE_GESTIONAR, "guardar el acta")
    if a.acta_document_id:
        raise ValidacionError("El acta de esta asamblea ya está en Documentos")
    sha = hashlib.sha256(pdf).hexdigest()
    storage = get_storage()
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        tenant_id=actor.tenant_id,
        uploaded_by=actor.user_id,
        title=f"Acta {a.consecutivo:03d} - {a.titulo}"[:255],
        original_filename=f"acta-{a.consecutivo:03d}.pdf",
        category=DocumentCategory.ACTAS,
        access_level=AccessLevel.PUBLIC,  # el acta es de todos los copropietarios
        status=DocumentStatus.UPLOADED,
        storage_key=storage.document_key(actor.tenant_id, doc_id, "original.pdf"),
        mime_type="application/pdf",
        size_bytes=len(pdf),
        sha256=sha,
        document_date=(a.abierta_at or a.fecha_hora).astimezone(TZ).date(),
        source="ASAMBLEA",
        source_ref=str(a.id),
    )
    await run_in_threadpool(storage.put_bytes, doc.storage_key, pdf, "application/pdf")
    db.add(doc)
    await db.flush()
    a.acta_document_id = doc.id
    await db.flush()
    return doc
