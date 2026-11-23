from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "ph",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.tasks.system",
        "app.workers.tasks.ingest",
        "app.workers.tasks.extract",
        "app.workers.tasks.reminders",
        "app.workers.tasks.quotes",
        "app.workers.tasks.minutes",
        "app.workers.tasks.demo",
        "app.workers.tasks.recaudos",
    ],
)

celery_app.conf.update(
    # Fiabilidad: si el worker muere a mitad de un OCR, la tarea vuelve a la cola
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    # Colas: ingesta pesada separada del resto
    task_default_queue="default",
    task_routes={"app.workers.tasks.ingest.*": {"queue": "ingestion"}},
    # Serialización / zona horaria
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Bogota",
    enable_utc=True,
    result_expires=60 * 60 * 24,
    # Tareas programadas (hora de Bogotá, ver timezone)
    beat_schedule={
        "recordatorios-vencimientos": {
            "task": "deadlines.send_reminders",
            "schedule": crontab(hour=7, minute=0),
        },
        # Solo actúa con DEMO_MODE=true: deja la demo pública como nueva cada noche
        "reinicio-demo": {
            "task": "demo.reset",
            "schedule": crontab(hour=4, minute=0),
        },
        "recaudos-transferencias-sin-verificar": {
            "task": "recaudos.transferencias_sin_verificar",
            "schedule": crontab(hour=8, minute=0),
        },
        "recaudos-corte-mensual": {
            "task": "recaudos.corte_mensual",
            "schedule": crontab(day_of_month=1, hour=6, minute=0),
        },
    },
)
