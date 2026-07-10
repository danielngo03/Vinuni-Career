"""Request schemas for the talent-pool search API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TalentSearchRequest(BaseModel):
    """A hiring need expressed as free text, a pasted/uploaded JD, and/or filters.

    At least one of ``query_text`` / ``jd_text`` / ``skills`` must be present
    (enforced in the service). ``jd_text`` carries an EXTERNAL JD — a job that is
    not yet posted — pasted by the partner. An uploaded JD FILE is extracted to
    text by the JD ingestion cascade at the router and passed in as ``jd_text``.
    """

    query_text: str | None = Field(default=None, max_length=1000)
    jd_text: str | None = Field(default=None, max_length=8000)
    skills: list[str] | None = Field(default=None, max_length=25)
    min_experience: int | None = Field(default=None, ge=0, le=50)
    limit: int = Field(default=12, ge=1, le=20)
    offset: int = Field(default=0, ge=0)
