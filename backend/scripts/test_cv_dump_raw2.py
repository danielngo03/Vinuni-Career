"""Quick dump for remaining problem files."""
from __future__ import annotations
import io, os, sys
from pathlib import Path
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)
import pdfplumber

CV_DIR = Path("/Users/anhtuan/Desktop/Vinuni/Build/C2-App-037/example/CV")
JD_DIR = Path("/Users/anhtuan/Desktop/Vinuni/Build/C2-App-037/example/JD")

for name, d in [("CV-PDF9.pdf", CV_DIR), ("CV-PDF10.pdf", CV_DIR), ("JD-PDF8.pdf", JD_DIR)]:
    path = d / name
    print(f"\n{'=' * 60}")
    print(f"FILE: {name}")
    print("=" * 60)
    with pdfplumber.open(io.BytesIO(path.read_bytes())) as pdf:
        for i, page in enumerate(pdf.pages[:2]):
            text = page.extract_text() or ""
            lines = text.splitlines()
            print(f"--- Page {i+1} first 25 lines ---")
            for ln in lines[:25]:
                print(repr(ln))
