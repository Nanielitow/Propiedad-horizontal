import logging

from app.core.config import get_settings
from app.services.demo import delete_orphan_files, restore_snapshot
from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(name="demo.reset")
def reset_demo() -> dict[str, object]:
    """Restauración nocturna de la demo pública (no hace nada si DEMO_MODE=false)."""
    if not get_settings().demo_mode:
        return {"skipped": "DEMO_MODE desactivado"}
    counts = restore_snapshot()
    removed = delete_orphan_files()
    return {"restored": counts, "orphan_files_removed": removed}
