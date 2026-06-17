from __future__ import annotations

import re
import unicodedata


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def strip_vietnamese_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    without_marks = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return without_marks.replace("Đ", "D").replace("đ", "d")


def slugify(value: str) -> str:
    ascii_value = strip_vietnamese_accents(value).lower()
    ascii_value = re.sub(r"[^a-z0-9]+", "-", ascii_value)
    return ascii_value.strip("-")
