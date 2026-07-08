"""Deterministic creative-policy PRE-checks (pure).

These are advisory pre-flags — they NEVER auto-approve or auto-reject a creative.
A creative stays ``pending`` and a human moderator still decides; the pre-check
only raises the obvious issues into the existing escalation/review queue so the
university does not have to eyeball every banner for the mechanical problems
(``docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md`` §5/§9 "admin-only policy review for
ad creative and targeting risk").

Four deterministic families (no AI, no I/O):

- ``creative_dimension_mismatch`` — the uploaded image aspect ratio is far from
  the slot's :data:`creatives.SLOT_SPECS` guidance (a squashed/stretched banner).
  ``creative_low_resolution`` — the image is too small for the slot.
- ``banned_claim`` — a banned marketing claim keyword (guaranteed job/visa,
  100% placement, get-rich, …) in the alt text.
- ``off_platform_contact`` — an email / phone / messaging-handle / mailto:/tel:
  pattern trying to move the student off-platform.
- ``disclosure_impersonation`` — alt copy on a PAID placement impersonating an
  official VinUni/university endorsement (faking the non-removable disclosure as
  editorial trust). The placement's own submit-time ``disclosure_confirmed`` gate
  is enforced elsewhere and is deliberately NOT re-flagged here (a draft creative
  is normally uploaded before disclosure is confirmed at submit).

Everything is a substring/regex/arithmetic check so the same creative always
yields the same findings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.advertising.domain import creatives as creative_vocab
from app.modules.advertising.domain import disclosure as disclosure_vocab

# Aspect-ratio tolerance (fraction of the target ratio) before a mismatch flags.
_RATIO_TOLERANCE = 0.18
# Below this on the short edge the banner is too low-res for a premium surface.
_MIN_SHORT_EDGE = 320

_SEVERITY_HIGH = "high"
_SEVERITY_MEDIUM = "medium"
_SEVERITY_LOW = "low"

# Banned marketing claims (vi + en), normalized to lowercase substrings.
_BANNED_CLAIMS: tuple[str, ...] = (
    "guaranteed job",
    "guaranteed visa",
    "visa guaranteed",
    "job guaranteed",
    "100% placement",
    "100% job",
    "get rich",
    "risk free",
    "no experience needed guaranteed",
    "cam kết việc làm",
    "đảm bảo việc làm",
    "bao đậu",
    "bao ra trường có việc",
    "cam kết visa",
    "đảm bảo visa",
    "làm giàu nhanh",
    "lương khủng",
    "việc nhẹ lương cao",
)

# Impersonation phrases that falsely imply an official university endorsement.
_IMPERSONATION_CLAIMS: tuple[str, ...] = (
    "official vinuni",
    "vinuni official",
    "endorsed by vinuni",
    "vinuni endorsed",
    "on behalf of vinuni",
    "chính thức của vinuni",
    "được vinuni chứng nhận",
    "đại diện vinuni",
    "vinuni bảo trợ",
)

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# 8+ digit run allowing spaces/()-. (a phone number), guarded by a leading digit/+.
_PHONE_RE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")
_HANDLE_RE = re.compile(
    r"\b(zalo|telegram|whats\s?app|wechat|viber|t\.me|line id|messenger)\b"
)
_CONTACT_SCHEME_RE = re.compile(r"\b(mailto:|tel:)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class PolicyFinding:
    """One deterministic pre-check finding (user-safe; no internals)."""

    code: str
    severity: str
    detail: str


def _parse_ratio(ratio: str | None) -> float | None:
    if not ratio or ":" not in ratio:
        return None
    left, _, right = ratio.partition(":")
    try:
        w = float(left)
        h = float(right)
    except ValueError:
        return None
    if h <= 0:
        return None
    return w / h


def _dimension_findings(
    slot: str, width: int | None, height: int | None
) -> list[PolicyFinding]:
    findings: list[PolicyFinding] = []
    if not width or not height or width <= 0 or height <= 0:
        return findings  # dimensions unknown -> skip (magic bytes already validated)

    spec = creative_vocab.slot_spec(slot)
    target = _parse_ratio(spec.get("desktop_ratio"))
    if target is not None:
        actual = width / height
        if abs(actual - target) / target > _RATIO_TOLERANCE:
            findings.append(
                PolicyFinding(
                    code="creative_dimension_mismatch",
                    severity=_SEVERITY_MEDIUM,
                    detail=(
                        f"aspect {width}x{height} deviates from slot guidance "
                        f"{spec.get('desktop_ratio')}"
                    ),
                )
            )
    if min(width, height) < _MIN_SHORT_EDGE:
        findings.append(
            PolicyFinding(
                code="creative_low_resolution",
                severity=_SEVERITY_LOW,
                detail=f"short edge {min(width, height)}px below {_MIN_SHORT_EDGE}px",
            )
        )
    return findings


def _text_findings(text: str, *, disclosure_class: str) -> list[PolicyFinding]:
    findings: list[PolicyFinding] = []
    lowered = text.lower()

    hit_claims = [c for c in _BANNED_CLAIMS if c in lowered]
    if hit_claims:
        findings.append(
            PolicyFinding(
                code="banned_claim",
                severity=_SEVERITY_HIGH,
                detail=f"banned claim(s): {', '.join(sorted(set(hit_claims)))}",
            )
        )

    if (
        _EMAIL_RE.search(text)
        or _PHONE_RE.search(text)
        or _HANDLE_RE.search(lowered)
        or _CONTACT_SCHEME_RE.search(text)
    ):
        findings.append(
            PolicyFinding(
                code="off_platform_contact",
                severity=_SEVERITY_HIGH,
                detail="off-platform contact pattern (email/phone/handle) detected",
            )
        )

    if disclosure_vocab.is_paid(disclosure_class):
        impersonation = [c for c in _IMPERSONATION_CLAIMS if c in lowered]
        if impersonation:
            findings.append(
                PolicyFinding(
                    code="disclosure_impersonation",
                    severity=_SEVERITY_HIGH,
                    detail="paid creative implies official university endorsement",
                )
            )

    return findings


def evaluate_creative(
    *,
    slot: str,
    width: int | None,
    height: int | None,
    alt_vi: str | None,
    alt_en: str | None,
    click_target: str | None,
    disclosure_class: str,
) -> list[PolicyFinding]:
    """Run every deterministic pre-check and return the findings (possibly empty)."""

    findings: list[PolicyFinding] = []
    findings.extend(_dimension_findings(slot, width, height))
    text = " ".join(part for part in (alt_vi, alt_en, click_target) if part)
    if text.strip():
        findings.extend(_text_findings(text, disclosure_class=disclosure_class))
    return findings


def overall_severity(findings: list[PolicyFinding]) -> str:
    """Collapse findings into the single queue severity (high > medium > low)."""

    order = {_SEVERITY_HIGH: 3, _SEVERITY_MEDIUM: 2, _SEVERITY_LOW: 1}
    best = max((order.get(f.severity, 0) for f in findings), default=0)
    for name, rank in order.items():
        if rank == best:
            return name
    return _SEVERITY_MEDIUM


def findings_payload(findings: list[PolicyFinding]) -> list[dict]:
    """User-safe list projection for API responses + queue findings (no internals)."""

    return [
        {"code": f.code, "severity": f.severity, "detail": f.detail} for f in findings
    ]
