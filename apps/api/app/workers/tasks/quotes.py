import logging
import uuid

from celery import Task

from app.services.extraction.quotes import mark_comparison_failed, run_comparison
from app.services.ingestion.errors import PermanentIngestionError
from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)

MAX_RETRIES = 2


@celery_app.task(bind=True, max_retries=MAX_RETRIES, soft_time_limit=420, time_limit=450)
def compare_quotes(self: Task, comparison_id: str, tenant_id: str) -> None:
    ids = (uuid.UUID(comparison_id), uuid.UUID(tenant_id))
    try:
        run_comparison(*ids)
    except PermanentIngestionError as exc:
        mark_comparison_failed(*ids, str(exc), final=True)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        final = self.request.retries >= MAX_RETRIES
        mark_comparison_failed(*ids, error, final=final)
        if not final:
            raise self.retry(exc=exc, countdown=60 * 2**self.request.retries) from exc
        log.exception("comparación de cotizaciones fallida %s", comparison_id)
        raise
