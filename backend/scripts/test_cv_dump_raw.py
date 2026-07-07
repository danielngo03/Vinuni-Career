"""Quick raw-text dump for debugging name/section detection issues.

Usage:
    cd backend && uv run python scripts/test_cv_dump_raw.py
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

import pdfplumber

CV_DIR = Path("/Users/anhtuan/Desktop/Vinuni/Build/C2-App-037/example/CV")

PROBLEM_PDFS = [
    "CV-PDF3.pdf",
    "CV-PDF6.pdf",
    "CV-PDF9.pdf",
    "CV-PDF10.pdf",
    "CV-PDF14.pdf",
]

for name in PROBLEM_PDFS:
    path = CV_DIR / name
    print(f"\n{'=' * 60}")
    print(f"FILE: {name}")
    print("=" * 60)
    with pdfplumber.open(io.BytesIO(path.read_bytes())) as pdf:
        for i, page in enumerate(pdf.pages[:2]):
            text = page.extract_text() or ""
            lines = text.splitlines()
            print(f"--- Page {i+1} first 30 lines ---")
            for ln in lines[:30]:
                print(repr(ln))
