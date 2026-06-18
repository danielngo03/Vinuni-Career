"""
Verification workflow activities.

These are plain async functions that can be called:
  1. Directly from the outbox poller (current asyncio mode).
  2. As Temporal activity functions when the Temporal worker is enabled.

The function signatures must NOT change between modes — only the caller changes.
"""
from __future__ import annotations

import logging

from app.shared.events import DomainEvent

logger = logging.getLogger(__name__)


async def on_registration_submitted(event: DomainEvent) -> None:
    """
    React to registration.submitted outbox event.

    In AUTO_LOW_RISK or SHADOW mode this triggers the verification pipeline:
    1. Load the RegistrationApplication + evidence already recorded.
    2. Run any pending provider checks (email domain, SIS lookup, business registry).
    3. Apply VerificationPolicy rules.
    4. If AUTO_LOW_RISK and all checks pass → approve.
    5. Otherwise → leave UNDER_REVIEW / emit admin notification.

    Currently delegates to the existing _record_initial_verification logic
    via a direct service call. Full async separation happens when Temporal
    worker is enabled.
    """
    aggregate_id = event.metadata.get("aggregate_id") or event.aggregate_id
    registration_type = event.metadata.get("registration_type", "STUDENT")

    logger.info(
        "verification_activity: registration.submitted id=%s type=%s",
        aggregate_id,
        registration_type,
    )

    # Import lazily to avoid circular startup dependency

    try:
        await _run_verification_policy_async(aggregate_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("verification_activity failed for %s: %s", aggregate_id, exc)


async def _run_verification_policy_async(application_id: str) -> None:
    """Call the synchronous policy runner in an executor to avoid blocking the loop."""
    import asyncio

    from app.modules.registrations.service import run_verification_and_maybe_approve
    from app.platform.database.session import SessionLocal

    def run() -> None:
        with SessionLocal() as db:
            run_verification_and_maybe_approve(db, application_id=application_id)

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, run)


async def on_document_uploaded(event: DomainEvent) -> None:
    """React to document.uploaded — trigger async scan."""
    document_id = event.metadata.get("aggregate_id") or event.aggregate_id
    storage_key = event.metadata.get("storage_key", "")
    logger.info("scan_activity: document.uploaded id=%s key=%s", document_id, storage_key)
    # In dev/test: mark CLEAN immediately (mock scan).
    # In production: submit to ClamAV or external scan service.
    await _mock_scan(document_id)


async def _mock_scan(document_id: str) -> None:
    """Development-mode scan: mark document CLEAN without real AV check."""
    import asyncio

    await asyncio.sleep(0.1)  # Simulate scan latency
    from app.modules.documents.application import RecordScanResultCommand, record_scan_result
    from app.modules.documents.infrastructure import SQLDocumentRepository
    from app.platform.database.session import SessionLocal

    with SessionLocal() as db:
        try:
            repo = SQLDocumentRepository(db)
            record_scan_result(
                RecordScanResultCommand(
                    document_id=document_id,
                    scan_result="CLEAN",
                    scan_engine="mock-dev-v1",
                    threats=[],
                ),
                repository=repo,
            )
            db.commit()
            logger.debug("mock scan: CLEAN for %s", document_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("mock scan failed for %s: %s", document_id, exc)
