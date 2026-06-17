from __future__ import annotations

from app.queue.celery_app import celery_app


@celery_app.task(name="sync.search_index")
def sync_search_index_task(entity_type: str, entity_id: str) -> dict[str, str]:
    return {"status": "queued", "entity_type": entity_type, "entity_id": entity_id}
