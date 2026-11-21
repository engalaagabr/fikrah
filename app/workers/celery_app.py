"""Celery configuration for Redis-backed FIKRAH jobs."""

from celery import Celery

from app.core.config import get_settings, get_worker_settings

settings = get_worker_settings()

celery_app = Celery(
    "fikrah",
    broker=get_settings().redis_url,
    include=["app.workers.tasks"],
)
celery_app.conf.update(
    task_ignore_result=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,
    task_reject_on_worker_lost=False,
    task_publish_retry=True,
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        "visibility_timeout": settings.broker_visibility_timeout_seconds
    },
    worker_prefetch_multiplier=1,
    beat_schedule={
        "deliver-durable-account-emails": {
            "task": "app.workers.tasks.deliver_account_emails",
            "schedule": float(settings.dispatch_interval_seconds),
        },
        "dispatch-durable-backend-jobs": {
            "task": "app.worker.tasks.dispatch_pending_work",
            "schedule": float(settings.dispatch_interval_seconds),
        }
    },
)
