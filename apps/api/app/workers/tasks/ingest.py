import logging
import uuid

from celery import Task

from app.models.enums import DEADLINE_CATEGORIES, DocumentCategory, JobStatus
from app.services.extraction.deadlines import enqueue_extraction
from app.services.extraction.minutes import enqueue_summary
from app.services.ingestion.errors import PermanentIngestionError
from app.services.ingestion.pipeline import _system_session, mark_job, run_ingestion
from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)

MAX_RETRIES = 3


@celery_app.task(bind=True, max_retries=MAX_RETRIES, soft_time_limit=900, time_limit=960)
def ingest_document(self: Task, job_id: str, tenant_id: str, document_id: str) -> None:
    ids = (uuid.UUID(job_id), uuid.UUID(tenant_id), uuid.UUID(document_id))
    try:
        category = run_ingestion(*ids)
    except PermanentIngestionError as exc:
        # No tiene sentido reintentar: se marca FAILED con un mensaje legible
        log.warning("ingesta fallida (permanente) documento=%s: %s", document_id, exc)
        mark_job(*ids, status=JobStatus.FAILED, error=str(exc))
    except Exception as exc:
        # Transitorio (red, S3, rate limit del proveedor de IA): backoff exponencial
        error = f"{type(exc).__name__}: {exc}"
        if self.request.retries < MAX_RETRIES:
            countdown = 30 * 2**self.request.retries  # 30s, 60s, 120s
            log.warning("ingesta reintento %s en %ss: %s", self.request.retries + 1, countdown, error)
            mark_job(*ids, status=JobStatus.RETRYING, error=error)
            raise self.retry(exc=exc, countdown=countdown) from exc
        log.exception("ingesta fallida tras %s reintentos documento=%s", MAX_RETRIES, document_id)
        mark_job(*ids, status=JobStatus.FAILED, error=error)
        raise
    else:
        # Encadenamiento: contratos, actas y mantenimientos pasan al detector de
        # vencimientos. Es un job aparte: si falla, el documento sigue disponible.
        if category in DEADLINE_CATEGORIES:
            try:
                with _system_session(ids[1]) as db:
                    enqueue_extraction(db, ids[1], ids[2])
            except Exception:
                log.exception("no se pudo encolar la extracción de vencimientos documento=%s", document_id)
        # Las actas, además, se resumen (acuerdos, votaciones, tareas)
        if category == DocumentCategory.ACTAS:
            try:
                with _system_session(ids[1]) as db:
                    enqueue_summary(db, ids[1], ids[2])
            except Exception:
                log.exception("no se pudo encolar el resumen del acta documento=%s", document_id)
