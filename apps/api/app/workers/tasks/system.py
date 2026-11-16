from app.workers.celery_app import celery_app


@celery_app.task(name="system.ping")
def ping() -> str:
    """Tarea de humo para verificar que broker y worker están conectados."""
    return "pong"
