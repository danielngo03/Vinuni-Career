from __future__ import annotations

from app.queue.celery_app import celery_app


@celery_app.task(name="email.send_notification")
def send_notification_task(to_email: str, subject: str, body: str) -> dict[str, str]:
    return {"status": "queued", "to_email": to_email, "subject": subject, "body": body}
