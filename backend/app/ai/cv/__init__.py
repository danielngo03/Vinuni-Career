"""CV AI task layer.

Produces grounded, non-destructive CV suggestion diffs through the AI gateway
(offline provider by default). Facts are grounded deterministically in the
provided structured sources so safety never depends on model compliance alone
(``docs/CV_STUDIO_SPEC.md`` §3; ``.claude/rules/ai.md``).
"""

from app.ai.cv.edit_command import generate_cv_edit_patch
from app.ai.cv.tasks import CvAiContext, CvAiResult, run_cv_task

__all__ = ["CvAiContext", "CvAiResult", "run_cv_task", "generate_cv_edit_patch"]
