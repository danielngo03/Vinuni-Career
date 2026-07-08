"""Seed ONE pending sponsored placement + pending creative so the university
moderation panel and partner creative manager have a real reviewable item to
browser-verify. Idempotent: removes any prior [DEMO-CREATIVE] rows first.

Local/dev only. Run from backend/:  python -m scripts.seed_demo_campaign_creative
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.core.db import get_sessionmaker
from app.core.metadata import import_all_models
from app.modules.auth.application.context import RequestContext

import_all_models()
from app.modules.advertising.application import creative_service
from app.modules.advertising.domain.models import CampaignCreative, SponsoredPlacement
from app.modules.users.domain.models import User
from app.shared.permissions import Principal

SUPERADMIN_EMAIL = "superadmin@vinuni.edu.vn"
TARGET_JOB_TITLE = "Backend Engineer Intern"
PAID_PACKAGE_NAME = "Được tài trợ 14 ngày"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 256
MARKER = "[DEMO-CREATIVE]"


async def main() -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        admin = (
            await session.execute(select(User).where(User.email == SUPERADMIN_EMAIL))
        ).scalar_one()

        # Resolve the target job (gives us the owning partner org).
        from app.modules.opportunities.domain.models import Job

        job = (
            await session.execute(
                select(Job).where(Job.title == TARGET_JOB_TITLE).limit(1)
            )
        ).scalar_one()

        from app.modules.advertising.domain.models import AdPackage

        pkg = (
            await session.execute(
                select(AdPackage).where(AdPackage.name == PAID_PACKAGE_NAME).limit(1)
            )
        ).scalar_one()

        # Idempotent cleanup of prior demo rows (creatives cascade with placement).
        prior = (
            await session.execute(
                select(SponsoredPlacement).where(
                    SponsoredPlacement.moderation_note == MARKER
                )
            )
        ).scalars().all()
        for p in prior:
            await session.execute(
                delete(CampaignCreative).where(CampaignCreative.placement_id == p.id)
            )
            await session.delete(p)
        await session.commit()

        now = datetime.now(tz=UTC)
        placement = SponsoredPlacement(
            org_id=job.org_id,
            created_by=admin.id,
            target_type="job",
            target_id=job.id,
            placement_type="sponsored",
            package_id=pkg.id,
            price_amount="3000000.00",
            currency="VND",
            start_at=now - timedelta(days=1),
            end_at=now + timedelta(days=13),
            status="pending_approval",
            disclosure_class="paid_sponsored",
            disclosure_confirmed=True,
            moderation_note=MARKER,
        )
        session.add(placement)
        await session.commit()
        await session.refresh(placement)

        principal = Principal(
            user_id=admin.id,
            persona="university_staff",
            org_id=None,
            is_superadmin=True,
        )
        ctx = RequestContext(ip="127.0.0.1", user_agent="seed")
        result = await creative_service.upload_creative(
            session,
            principal=principal,
            placement_id=placement.id,
            slot="homepage_hero",
            data=PNG_BYTES,
            content_type="image/png",
            alt_vi="Banner tuyển dụng Acme (demo)",
            alt_en="Acme hiring banner (demo)",
            focal_x=0.4,
            focal_y=0.55,
            click_target="/vi/jobs",
            ctx=ctx,
        )
        print(
            "seeded placement", placement.id,
            "status=pending_approval disclosure=paid_sponsored creative=",
            result.get("id"),
        )


if __name__ == "__main__":
    asyncio.run(main())
