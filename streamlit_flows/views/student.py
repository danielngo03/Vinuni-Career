from __future__ import annotations

from .student_profile import render_student_profile_page

def render_student_page(api_base: str, token: str) -> None:
    """Backward-compatible wrapper for existing routes/imports."""
    render_student_profile_page(api_base, token)
