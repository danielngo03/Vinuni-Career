from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter

router = APIRouter()

DATA_ROOT = Path(__file__).resolve().parents[4] / ".data" / "demo"
COMPANIES_DIR = DATA_ROOT / "companies"


@router.get("")
def list_companies() -> list[dict[str, Any]]:
    if not COMPANIES_DIR.exists():
        return []
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(COMPANIES_DIR.glob("*.json"))
    ]
