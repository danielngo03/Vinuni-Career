from __future__ import annotations

import pytest
from scripts.seed_workflow_templates import seed_templates

from tests.auth_utils import CTX
from tests.org_utils import make_org_with_admin


@pytest.mark.asyncio
async def test_seed_creates_both_templates_active(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")

    flows = await seed_templates(db_session, principal=admin, ctx=CTX)

    assert {f.name for f in flows} == {"Student verification", "Partner/employer account approval"}
    assert all(f.status == "ACTIVE" for f in flows)


@pytest.mark.asyncio
async def test_seed_is_idempotent(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")

    first = await seed_templates(db_session, principal=admin, ctx=CTX)
    second = await seed_templates(db_session, principal=admin, ctx=CTX)

    assert {f.id for f in first} == {f.id for f in second}
