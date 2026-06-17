from __future__ import annotations

from app.queue.celery_app import celery_app
from app.services.ai_service import mask_pii, match_cv_to_job


@celery_app.task(name="ai.mask_cv")
def mask_cv_task(text: str) -> dict:
    masked_text, entities = mask_pii(text)
    return {"masked_text": masked_text, "entities": entities}


@celery_app.task(name="ai.match_cv_to_job")
def match_cv_to_job_task(cv_text: str, job_description: str) -> dict:
    return match_cv_to_job(cv_text, job_description).model_dump()
