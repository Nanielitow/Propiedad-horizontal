import logging
import uuid

from celery import Task

from app.models.enums import JobStatus
from app.services.extraction.minutes import run_summarize
from app.services.ingestion.errors import PermanentIngestionError
from app.services.ingestion.pipeline import mark_job
from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)

MAX_RETRIES = 3


@celery_app.task(bind=True, max_retries=MAX_RETRIES, soft_time_limit=300, time_limit=330)
def summarize_minutes(self: Task, job_id: str, tenant_id: str, document_id: str) -> None:
    ids = (uuid.UUID(job_id), uuid.UUID(tenant_id), uuid.UUID(document_id))
    try:
        run_summarize(*ids)
    except PermanentIngestionError as exc:
        mark_job(*ids, status=JobStatus.FAILED, error=str(exc), fail_document=False)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        if self.request.retries < MAX_RETRIES:
            mark_job(*ids, status=JobStatus.RETRYING, error=error, fail_document=False)
            raise self.retry(exc=exc, countdown=60 * 2**self.request.retries) from exc
        log.exception("resumen de acta fallido documento=%s", document_id)
        mark_job(*ids, status=JobStatus.FAILED, error=error, fail_document=False)
        raise
