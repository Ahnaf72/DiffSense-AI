"""Health-check and test tasks."""

import time

from app.core.worker import celery_app


@celery_app.task(name="app.tasks.health.ping")
def ping() -> str:
    """Simple test task — returns 'pong'."""
    return "pong"


@celery_app.task(bind=True, name="app.tasks.health.slow_add")
def slow_add(self, x: int, y: int, delay: float = 3.0) -> int:
    """Test task that simulates slow work with progress updates."""
    for i in range(int(delay)):
        self.update_state(state="PROGRESS", meta={"step": i + 1, "total": int(delay)})
        time.sleep(1)
    return x + y
