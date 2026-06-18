"""Institution — domain layer: VerificationPolicy value object."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PolicyMode(StrEnum):
    DISABLED = "DISABLED"
    SHADOW = "SHADOW"
    AUTO_LOW_RISK = "AUTO_LOW_RISK"


@dataclass(frozen=True)
class VerificationPolicyConfig:
    """Read-only domain view of a verification policy."""

    university_org_id: str
    registration_type: str
    mode: PolicyMode
    global_kill_switch: bool
    confidence_threshold: int
    required_providers: list[str]
    required_documents: list[str]
    sample_rate: int
    model_version: str

    def is_auto_approve_enabled(self) -> bool:
        return (
            self.mode == PolicyMode.AUTO_LOW_RISK
            and not self.global_kill_switch
        )

    def is_shadow(self) -> bool:
        return self.mode == PolicyMode.SHADOW and not self.global_kill_switch
