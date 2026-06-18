from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

FileKind = Literal["pdf", "docx", "text", "image", "unknown"]
IngestionRoute = Literal["reject", "text_extraction", "vision_extraction"]


@dataclass(frozen=True)
class IngestionDecision:
    route: IngestionRoute
    detected_kind: FileKind
    declared_content_type: str | None
    byte_size: int
    reasons: list[str] = field(default_factory=list)
    extracted_text_preview: str = ""
    metadata: dict[str, int | str | bool] = field(default_factory=dict)

    @property
    def accepted(self) -> bool:
        return self.route != "reject"

    @property
    def needs_vision(self) -> bool:
        return self.route == "vision_extraction"
