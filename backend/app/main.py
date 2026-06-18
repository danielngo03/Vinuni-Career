"""
Entry point for the backend API.

Usage:
  uvicorn app.main:app --reload
"""
from __future__ import annotations

from app.bootstrap import create_app

app = create_app()
