"""Herramientas de la demo pública.

  python -m app.scripts.demo load               # sube y procesa los documentos de ejemplo
  python -m app.scripts.demo recaudos           # genera ~6 semanas de movimientos del módulo de recaudos
  python -m app.scripts.demo snapshot           # guarda el estado actual como "demo limpia"
  python -m app.scripts.demo restore            # vuelve a la instantánea (lo hace beat cada noche)
  python -m app.scripts.demo configure-bucket   # CORS del bucket para el dominio de la app

Orden en un servidor nuevo:  migraciones -> seed -> load -> recaudos -> (revisar en la web) -> snapshot
"""

import hashlib
import sys
import time
import uuid
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.db.rls import set_rls_context_sync
from app.db.session import SyncSessionLocal
from app.models import Document, ProcessingJob, QuoteComparison, QuoteComparisonDocument, Tenant, User
from app.models.enums import AccessLevel, DocumentCategory, DocumentStatus, JobStatus, JobType
from app.scripts import make_sample_pdfs
from app.services.demo import delete_orphan_files, restore_snapshot, save_snapshot
from app.services.extraction.quotes import COMPARE_TASK
from app.services.storage.s3 import get_storage
from app.workers.celery_app import celery_app

C = DocumentCategory
SAMPLES = [  # (archivo generado, categoría, título visible)
    ("manual_convivencia_demo.pdf", C.CONVIVENCIA, "Manual de convivencia"),
    ("acta_asamblea_escaneada_demo.pdf", C.ACTAS, "Acta 012 - Asamblea ordinaria (escaneada)"),
    ("acta_asamblea_extraordinaria_demo.pdf", C.ACTAS, "Acta 013 - Asamblea extraordinaria"),
    ("poliza_areas_comunes_demo.pdf", C.CONTRATOS, "Póliza de áreas comunes 2026-2027"),
    ("contrato_vigilancia_demo.pdf", C.CONTRATOS, "Contrato de vigilancia - Seguridad Atlas"),
    ("certificado_lavado_tanques_escaneado_demo.pdf", C.MANTENIMIENTO, "Certificado lavado de tanques (escaneado)"),
    ("cotizacion_cubiertas_andinas_demo.pdf", C.COTIZACIONES, "Cotización Cubiertas Andinas"),
    ("cotizacion_impertec_demo.pdf", C.COTIZACIONES, "Cotización ImperTec"),
    ("cotizacion_techos_pro_escaneada_demo.pdf", C.COTIZACIONES, "Cotización Techos Pro (escaneada)"),
]
TENANT_SLUG = "los-pinos"
ADMIN_EMAIL = "admin@lospinos.demo"
COMPARISON_TITLE = "Impermeabilización cubierta torre 2"
RUNNING = {JobStatus.PENDING, JobStatus.RUNNING, JobStatus.RETRYING}
INGEST_TASK = "app.workers.tasks.ingest.ingest_document"


def _context():  # type: ignore[no-untyped-def]
    db = SyncSessionLocal()
    tenant = db.scalar(select(Tenant).where(Tenant.slug == TENANT_SLUG))
    admin = db.scalar(select(User).where(User.email == ADMIN_EMAIL))
    if tenant is None or admin is None:
        sys.exit("Faltan los datos base: ejecute primero `python -m app.scripts.seed`")
    set_rls_context_sync(db, tenant_id=tenant.id, role="SYSTEM")
    return db, tenant, admin


def _wait(db, tenant_id: uuid.UUID, what: str, timeout_s: int = 1200) -> None:  # type: ignore[no-untyped-def]
    start = time.time()
    while time.time() - start < timeout_s:
        db.expire_all()
        busy_jobs = db.scalar(
            select(ProcessingJob.id)
            .where(ProcessingJob.tenant_id == tenant_id, ProcessingJob.status.in_(RUNNING))
            .limit(1)
        )
        busy_docs = db.scalar(
            select(Document.id)
            .where(
                Document.tenant_id == tenant_id, Document.status.in_([DocumentStatus.QUEUED, DocumentStatus.PROCESSING])
            )
            .limit(1)
        )
        busy_cmp = db.scalar(
            select(QuoteComparison.id)
            .where(QuoteComparison.tenant_id == tenant_id, QuoteComparison.status.in_(RUNNING))
            .limit(1)
        )
        if not (busy_jobs or busy_docs or busy_cmp):
            print(f"  {what}: listo en {time.time() - start:.0f} s")
            return
        time.sleep(5)
    sys.exit(f"Tiempo agotado esperando: {what}")


def load() -> None:
    make_sample_pdfs.main()
    samples_dir = Path(make_sample_pdfs.OUT)
    storage = get_storage()
    db, tenant, admin = _context()

    print("Subiendo documentos de demostración…")
    for filename, category, title in SAMPLES:
        path = samples_dir / filename
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if db.scalar(select(Document.id).where(Document.tenant_id == tenant.id, Document.sha256 == sha)):
            print(f"  ya existe: {title}")
            continue
        doc_id = uuid.uuid4()
        key = storage.document_key(tenant.id, doc_id, "original.pdf")
        storage.upload(path, key)
        public = category in {C.CONVIVENCIA, C.COMUNICADOS}
        db.add(
            Document(
                id=doc_id,
                tenant_id=tenant.id,
                uploaded_by=admin.id,
                title=title,
                original_filename=filename,
                category=category,
                access_level=AccessLevel.PUBLIC if public else AccessLevel.ADMIN,
                status=DocumentStatus.QUEUED,
                storage_key=key,
                size_bytes=len(data),
                sha256=sha,
            )
        )
        job = ProcessingJob(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            document_id=doc_id,
            type=JobType.INGEST,
            status=JobStatus.PENDING,
            attempts=0,
            payload={},
        )
        db.add(job)
        db.commit()  # commit antes de encolar
        celery_app.send_task(INGEST_TASK, args=[str(job.id), str(tenant.id), str(doc_id)])
        print(f"  encolado: {title}")

    print("Procesando (OCR, indexación, vencimientos y actas)…")
    _wait(db, tenant.id, "documentos")

    if not db.scalar(
        select(QuoteComparison.id).where(
            QuoteComparison.tenant_id == tenant.id, QuoteComparison.title == COMPARISON_TITLE
        )
    ):
        quotes = list(
            db.scalars(
                select(Document).where(
                    Document.tenant_id == tenant.id,
                    Document.category == C.COTIZACIONES,
                    Document.status == DocumentStatus.READY,
                )
            )
        )
        if len(quotes) >= 2:
            comparison = QuoteComparison(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                created_by=admin.id,
                title=COMPARISON_TITLE,
                status=JobStatus.PENDING,
                result={"progress": "queued"},
            )
            db.add(comparison)
            db.flush()
            for q in quotes:
                db.add(QuoteComparisonDocument(tenant_id=tenant.id, comparison_id=comparison.id, document_id=q.id))
            db.commit()
            celery_app.send_task(COMPARE_TASK, args=[str(comparison.id), str(tenant.id)])
            print("Comparando cotizaciones…")
            _wait(db, tenant.id, "comparación")

    docs = list(db.scalars(select(Document).where(Document.tenant_id == tenant.id)))
    failed = [d.title for d in docs if d.status == DocumentStatus.FAILED]
    print(f"\nDemo cargada: {len(docs)} documentos" + (f" · CON ERROR: {', '.join(failed)}" if failed else ""))
    print("Revísela en la web y, si todo está bien:  python -m app.scripts.demo snapshot")
    db.close()


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "load":
        load()
    elif command == "recaudos":
        from app.scripts.demo_recaudos import main as recaudos

        recaudos()
    elif command == "snapshot":
        counts = save_snapshot()
        print("Instantánea guardada:", ", ".join(f"{t}={n}" for t, n in counts.items() if n))
    elif command == "restore":
        counts = restore_snapshot()
        removed = delete_orphan_files()
        print(
            "Demo restaurada:",
            ", ".join(f"{t}={n}" for t, n in counts.items() if n),
            f"· archivos huérfanos: {removed}",
        )
    elif command == "configure-bucket":
        origin = get_settings().app_url.rstrip("/")
        get_storage().configure_cors([origin])
        print(f"CORS configurado en el bucket para {origin}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
