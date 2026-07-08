from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PlatformFontUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # One of the keys from FONT_CATALOGUE. Send null to reset to platform default.
    font_key: str | None = Field(default=None, max_length=50)
