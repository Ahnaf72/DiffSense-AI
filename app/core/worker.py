"""Celery application instance — import this from tasks and from the FastAPI app."""

from __future__ import annotations

from celery import Celery

from app.core.config import settings

broker = settings.celery_broker_url or settings.redis_url
backend = settings.celery_result_backend or settings.redis_url

celery_app = Celery(
    "diffsense-worker",
    broker=broker,
    backend=backend,
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timeouts
    task_soft_time_limit=300,   # 5 min soft limit
    task_time_limit=600,        # 10 min hard kill

    # Reliability
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    worker_concurrency=4,

    # Results
    result_expires=3600,        # results kept 1 hour

    # Retry configuration
    task_reject_on_worker_lost=True,
    task_track_started=True,
)

# Import task modules so @celery_app.task decorators register them
import app.tasks.health   # noqa: F401
import app.tasks.documents   # noqa: F401
import app.tasks.reports   # noqa: F401
