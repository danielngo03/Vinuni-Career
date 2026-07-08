"""Unit tests for structured salary_mode / experience_mode (B-544 / B-545).

Covers:
- Schema-level validation (`JobCreateRequest`) for every salary_mode/
  experience_mode value: valid combos pass, invalid combos raise (-> 422 at
  the API layer via Pydantic ValidationError).
- `salary_mode` being authoritative over a client-sent `salary_is_disclosed`.
- Presenter output (`_salary_display` / `_experience_display`) for the
  stored-mode path (every mode) and the legacy null-combination inference
  fallback path (mode absent).
- Presenter `_salary` raw block: owner sees real numbers for `hidden` mode;
  public/non-owner never does.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.opportunities.api import presenters
from app.modules.opportunities.api.schemas import (
    JobCreateRequest,
    validate_experience_mode,
    validate_salary_mode,
)
from app.modules.opportunities.domain.models import Job
from pydantic import ValidationError


def _create_payload(**overrides) -> dict:
    base = {
        "title": "Backend Intern",
        "description": "We are hiring a backend intern to build APIs.",
        "employment_type": "internship",
        "location_type": "onsite",
        "location_country": "Vietnam",
    }
    base.update(overrides)
    return base


def _job(**overrides) -> Job:
    defaults = {
        "id": uuid.uuid4(),
        "org_id": uuid.uuid4(),
        "posted_by": uuid.uuid4(),
        "title": "Backend Intern",
        "slug": f"backend-intern-{uuid.uuid4().hex[:6]}",
        "description": "desc",
        "employment_type": "internship",
        "location_type": "onsite",
        "location_country": "Vietnam",
        "locations": [],
        "required_skills": [],
        "preferred_skills": [],
        "salary_currency": "VND",
        "salary_is_disclosed": False,
        "salary_min": None,
        "salary_max": None,
        "salary_mode": None,
        "salary_period": "monthly",
        "salary_gross_net": "unspecified",
        "experience_min_years": None,
        "experience_max_years": None,
        "experience_mode": None,
        "candidate_requirements": {},
        "headcount": 1,
    }
    defaults.update(overrides)
    return Job(**defaults)


# --------------------------------------------------------------------------- #
# Schema validation: salary_mode                                             #
# --------------------------------------------------------------------------- #


def test_salary_mode_negotiable_requires_empty_min_max() -> None:
    req = JobCreateRequest(**_create_payload(salary_mode="negotiable"))
    assert req.salary_mode == "negotiable"
    assert req.salary_is_disclosed is False

    with pytest.raises(ValidationError):
        JobCreateRequest(**_create_payload(salary_mode="negotiable", salary_min=1000))


def test_salary_mode_hidden_allows_real_numbers_but_not_disclosed() -> None:
    req = JobCreateRequest(
        **_create_payload(salary_mode="hidden", salary_min=10_000_000, salary_max=15_000_000)
    )
    assert req.salary_mode == "hidden"
    assert req.salary_is_disclosed is False
    assert req.salary_min == 10_000_000


def test_salary_mode_fixed_requires_equal_min_max() -> None:
    req = JobCreateRequest(
        **_create_payload(salary_mode="fixed", salary_min=15_000_000, salary_max=15_000_000)
    )
    assert req.salary_is_disclosed is True

    with pytest.raises(ValidationError):
        JobCreateRequest(
            **_create_payload(salary_mode="fixed", salary_min=15_000_000, salary_max=20_000_000)
        )
    with pytest.raises(ValidationError):
        JobCreateRequest(**_create_payload(salary_mode="fixed", salary_min=15_000_000))


def test_salary_mode_range_requires_min_lt_max() -> None:
    req = JobCreateRequest(
        **_create_payload(salary_mode="range", salary_min=10_000_000, salary_max=20_000_000)
    )
    assert req.salary_is_disclosed is True

    with pytest.raises(ValidationError):
        JobCreateRequest(
            **_create_payload(salary_mode="range", salary_min=20_000_000, salary_max=10_000_000)
        )
    with pytest.raises(ValidationError):
        JobCreateRequest(
            **_create_payload(salary_mode="range", salary_min=20_000_000, salary_max=20_000_000)
        )


def test_salary_mode_from_requires_min_only() -> None:
    req = JobCreateRequest(**_create_payload(salary_mode="from", salary_min=10_000_000))
    assert req.salary_is_disclosed is True
    assert req.salary_max is None

    with pytest.raises(ValidationError):
        JobCreateRequest(
            **_create_payload(salary_mode="from", salary_min=10_000_000, salary_max=20_000_000)
        )
    with pytest.raises(ValidationError):
        JobCreateRequest(**_create_payload(salary_mode="from"))


def test_salary_mode_to_requires_max_only() -> None:
    req = JobCreateRequest(**_create_payload(salary_mode="to", salary_max=20_000_000))
    assert req.salary_is_disclosed is True
    assert req.salary_min is None

    with pytest.raises(ValidationError):
        JobCreateRequest(
            **_create_payload(salary_mode="to", salary_min=10_000_000, salary_max=20_000_000)
        )


def test_salary_mode_authoritative_over_client_disclosed_flag() -> None:
    """A client sending a contradictory salary_is_disclosed is overridden by mode."""
    req = JobCreateRequest(
        **_create_payload(
            salary_mode="negotiable", salary_is_disclosed=True,
        )
    )
    assert req.salary_is_disclosed is False

    req2 = JobCreateRequest(
        **_create_payload(
            salary_mode="fixed", salary_min=1, salary_max=1, salary_is_disclosed=False,
        )
    )
    assert req2.salary_is_disclosed is True


def test_salary_mode_invalid_value_rejected() -> None:
    with pytest.raises(ValidationError):
        JobCreateRequest(**_create_payload(salary_mode="bogus"))


def test_salary_period_and_gross_net_vocabulary() -> None:
    with pytest.raises(ValidationError):
        JobCreateRequest(**_create_payload(salary_period="weekly"))
    with pytest.raises(ValidationError):
        JobCreateRequest(**_create_payload(salary_gross_net="net_of_tax"))
    req = JobCreateRequest(**_create_payload(salary_period="yearly", salary_gross_net="gross"))
    assert req.salary_period == "yearly"
    assert req.salary_gross_net == "gross"


# --------------------------------------------------------------------------- #
# Schema validation: experience_mode                                         #
# --------------------------------------------------------------------------- #


def test_experience_mode_no_requirement_requires_empty_years() -> None:
    req = JobCreateRequest(**_create_payload(experience_mode="no_requirement"))
    assert req.experience_mode == "no_requirement"
    with pytest.raises(ValidationError):
        JobCreateRequest(
            **_create_payload(experience_mode="no_requirement", experience_min_years=1)
        )


def test_experience_mode_fresher_requires_zero_zero() -> None:
    req = JobCreateRequest(
        **_create_payload(
            experience_mode="fresher", experience_min_years=0, experience_max_years=0
        )
    )
    assert req.experience_mode == "fresher"
    with pytest.raises(ValidationError):
        JobCreateRequest(
            **_create_payload(
                experience_mode="fresher", experience_min_years=0, experience_max_years=1
            )
        )


def test_experience_mode_range_requires_min_lt_max() -> None:
    JobCreateRequest(
        **_create_payload(
            experience_mode="range", experience_min_years=1, experience_max_years=3
        )
    )
    with pytest.raises(ValidationError):
        JobCreateRequest(
            **_create_payload(
                experience_mode="range", experience_min_years=3, experience_max_years=1
            )
        )
    with pytest.raises(ValidationError):
        JobCreateRequest(
            **_create_payload(
                experience_mode="range", experience_min_years=3, experience_max_years=3
            )
        )


def test_experience_mode_min_and_max() -> None:
    req_min = JobCreateRequest(
        **_create_payload(experience_mode="min", experience_min_years=2)
    )
    assert req_min.experience_max_years is None
    req_max = JobCreateRequest(
        **_create_payload(experience_mode="max", experience_max_years=5)
    )
    assert req_max.experience_min_years is None

    with pytest.raises(ValidationError):
        JobCreateRequest(
            **_create_payload(
                experience_mode="min", experience_min_years=2, experience_max_years=5
            )
        )


# --------------------------------------------------------------------------- #
# Direct validator function tests (used by job_service for merged PATCH state)
# --------------------------------------------------------------------------- #


def test_validate_salary_mode_function_raises_value_error_on_bad_combo() -> None:
    with pytest.raises(ValueError):
        validate_salary_mode(
            salary_mode="range", salary_min=10, salary_max=5, salary_is_disclosed=False,
        )


def test_validate_experience_mode_function_raises_value_error_on_bad_combo() -> None:
    with pytest.raises(ValueError):
        validate_experience_mode(
            experience_mode="fresher", experience_min_years=1, experience_max_years=0,
        )


# --------------------------------------------------------------------------- #
# Presenter: stored-mode path                                                #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "mode,min_amount,max_amount,disclosed,expected_kind",
    [
        ("negotiable", None, None, False, "negotiable"),
        ("hidden", 10_000_000, 15_000_000, False, "hidden"),
        ("fixed", 15_000_000, 15_000_000, True, "fixed"),
        ("range", 10_000_000, 20_000_000, True, "range"),
        ("from", 10_000_000, None, True, "from"),
        ("to", None, 20_000_000, True, "to"),
    ],
)
def test_salary_display_prefers_stored_mode(
    mode, min_amount, max_amount, disclosed, expected_kind
) -> None:
    job = _job(
        salary_mode=mode,
        salary_min=min_amount,
        salary_max=max_amount,
        salary_is_disclosed=disclosed,
        salary_period="yearly",
        salary_gross_net="gross",
    )
    display = presenters._salary_display(job, locale="en")
    assert display["kind"] == expected_kind
    assert display["period"] == "yearly"
    assert display["gross_net"] == "gross"


def test_salary_raw_block_hides_hidden_mode_from_public_but_shows_owner() -> None:
    job = _job(
        salary_mode="hidden", salary_min=10_000_000, salary_max=15_000_000,
        salary_is_disclosed=False,
    )
    assert presenters._salary(job, is_owner=False) is None
    owner_view = presenters._salary(job, is_owner=True)
    assert owner_view == {"min": 10_000_000, "max": 15_000_000, "currency": "VND"}


def test_salary_raw_block_negotiable_hidden_from_everyone() -> None:
    job = _job(
        salary_mode="negotiable", salary_min=None, salary_max=None,
        salary_is_disclosed=False,
    )
    assert presenters._salary(job, is_owner=False) is None
    assert presenters._salary(job, is_owner=True) is None


@pytest.mark.parametrize(
    "mode,min_years,max_years,expected_kind",
    [
        ("no_requirement", None, None, "no_requirement"),
        ("fresher", 0, 0, "fresher"),
        ("range", 1, 3, "range"),
        ("min", 2, None, "min"),
        ("max", None, 5, "max"),
    ],
)
def test_experience_display_prefers_stored_mode(mode, min_years, max_years, expected_kind) -> None:
    job = _job(experience_mode=mode, experience_min_years=min_years, experience_max_years=max_years)
    display = presenters._experience_display(job, locale="en")
    assert display["kind"] == expected_kind


# --------------------------------------------------------------------------- #
# Presenter: legacy inference fallback (mode absent)                         #
# --------------------------------------------------------------------------- #


def test_salary_display_legacy_fallback_when_mode_missing() -> None:
    job = _job(salary_mode=None, salary_min=None, salary_max=None, salary_is_disclosed=False)
    display = presenters._salary_display(job, locale="vi")
    assert display["kind"] == "negotiable"

    job2 = _job(
        salary_mode=None, salary_min=15_000_000, salary_max=15_000_000,
        salary_is_disclosed=True,
    )
    display2 = presenters._salary_display(job2, locale="vi")
    assert display2["kind"] == "fixed"

    job3 = _job(salary_mode=None, salary_min=None, salary_max=20_000_000, salary_is_disclosed=True)
    display3 = presenters._salary_display(job3, locale="vi")
    assert display3["kind"] == "to"


def test_experience_display_legacy_fallback_when_mode_missing() -> None:
    job = _job(experience_mode=None, experience_min_years=None, experience_max_years=None)
    display = presenters._experience_display(job, locale="vi")
    assert display["kind"] == "not_required"

    job2 = _job(experience_mode=None, experience_min_years=None, experience_max_years=3)
    display2 = presenters._experience_display(job2, locale="vi")
    assert display2["kind"] == "up_to"
