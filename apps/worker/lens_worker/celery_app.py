"""Celery application. Broker/backend: Redis (SPEC.md §2.1)."""

from __future__ import annotations

from celery import Celery

from lens_api.settings import get_settings

settings = get_settings()

app = Celery(
    "lens",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["lens_worker.tasks"],
)
app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="lens.eval",
    task_routes={
        "lens.evaluate_trace": {"queue": "lens.eval"},
        "lens.run_dataset_eval": {"queue": "lens.eval"},
        "lens.run_redteam": {"queue": "lens.redteam"},
    },
)
