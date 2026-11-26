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


@celery_app.task(name="demo.restablecer_conjuntos")
def restablecer_conjuntos() -> dict[str, object]:
    """Desde el panel de la plataforma: deja como nuevos solo los conjuntos de demostración (no toca los reales)."""
    from app.services.demo import restablecer_conjuntos_demo

    counts = restablecer_conjuntos_demo()
    return {"restablecidos": sum(counts.values())}
