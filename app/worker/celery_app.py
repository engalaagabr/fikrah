"""Celery configuration for Redis-backed FIKRAH jobs."""

import os

from celery import Celery

from app.worker.config import WorkerSettings

settings = WorkerSettings.from_env()

celery_app = Celery(
    "fikrah",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    include=["app.worker.tasks"],
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
    broker_transport_options={"visibility_timeout": settings.broker_visibility_timeout_seconds},
    worker_prefetch_multiplier=1,
    beat_schedule={
        "dispatch-durable-backend-jobs": {
            "task": "app.worker.tasks.dispatch_pending_work",
            "schedule": float(settings.dispatch_interval_seconds),
        }
    },
)
