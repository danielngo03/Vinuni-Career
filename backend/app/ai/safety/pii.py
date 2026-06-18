from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?84|0)(?:[\s.-]?\d){8,10}(?!\d)")
LINKEDIN_RE = re.compile(r"\b(?:https?://)?(?:www\.)?linkedin\.com/[^\s,;]+", re.IGNORECASE)
URL_RE = re.compile(r"\bhttps?://[^\s,;]+", re.IGNORECASE)
VIETNAM_ID_RE = re.compile(r"(?<!\d)\d{9}|\d{12}(?!\d)")
ADDRESS_HINT_RE = re.compile(
    r"\b(address|dia chi|địa chỉ|phuong|phường|quan|quận|district|ward)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PIIEntity:
    type: str
    value: str
    start: int
    end: int

    def to_dict(self) -> dict[str, str]:
        payload = asdict(self)
        return {key: str(value) for key, value in payload.items()}


def mask_pii(text: str) -> tuple[str, list[dict[str, str]]]:
    entities: list[PIIEntity] = []

    def collect(pattern: re.Pattern[str], label: str) -> None:
        for match in pattern.finditer(text):
            entities.append(PIIEntity(label, match.group(0), match.start(), match.end()))

    collect(EMAIL_RE, "EMAIL")
    collect(PHONE_RE, "PHONE")
    collect(LINKEDIN_RE, "PROFILE_URL")
    collect(URL_RE, "URL")
    collect(VIETNAM_ID_RE, "GOVERNMENT_ID")

    lines = text.splitlines()
    offset = 0
    for line in lines[:8]:
        stripped = line.strip()
        if _looks_like_name(stripped):
            start = offset + line.index(stripped)
            entities.append(PIIEntity("POSSIBLE_NAME", stripped, start, start + len(stripped)))
            break
        offset += len(line) + 1

    masked = text
    non_overlapping = _without_overlaps(entities)
    for entity in sorted(non_overlapping, key=lambda item: item.start, reverse=True):
        replacement = f"[REDACTED_{entity.type}]"
        masked = masked[: entity.start] + replacement + masked[entity.end :]

    masked_lines = []
    for line in masked.splitlines():
        if ADDRESS_HINT_RE.search(_strip_accents(line)) and len(line) < 240:
            masked_lines.append("[REDACTED_ADDRESS]")
        else:
            masked_lines.append(line)
    masked = "\n".join(masked_lines)

    return masked, [entity.to_dict() for entity in non_overlapping]


def _looks_like_name(value: str) -> bool:
    if not value or any(char.isdigit() for char in value):
        return False
    if any(marker in value for marker in ("@", ":", "/", "\\")):
        return False
    words = value.split()
    if not 2 <= len(words) <= 5:
        return False
    lowered = value.lower()
    blocked = {"curriculum vitae", "resume", "cv", "profile", "education", "experience"}
    return lowered not in blocked and all(len(word) >= 2 or word.isalpha() for word in words)


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.replace("Đ", "D").replace("đ", "d"))
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn").lower()


def _without_overlaps(entities: list[PIIEntity]) -> list[PIIEntity]:
    priority = {"EMAIL": 10, "PHONE": 9, "PROFILE_URL": 8, "URL": 7, "POSSIBLE_NAME": 6}
    selected: list[PIIEntity] = []
    for entity in sorted(
        entities,
        key=lambda item: (item.start, -(priority.get(item.type, 0)), -(item.end - item.start)),
    ):
        if any(entity.start < other.end and entity.end > other.start for other in selected):
            continue
        selected.append(entity)
    return sorted(selected, key=lambda item: item.start)
