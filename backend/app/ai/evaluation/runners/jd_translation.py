"""Eval runner + checker for the ``jd_translation`` family.

Exercises the real ``translation_service._ai_translate`` pipeline — prompt
construction, JSON-shape parsing, and the three-tier degrade chain (AI ->
machine-translation draft -> ``None``). Two I/O boundaries are mocked to stay
offline/deterministic: the network-calling machine-translation draft
(``_machine_translate_job``, which would otherwise call the real
``deep-translator``/Google Translate service) and the AI gateway call
itself (``AiTaskRunner.complete``, patched with a canned JSON/error response
— exactly like ``jd_extraction.py`` stubs its two I/O boundaries). The DB
cache layer (``get_or_create_translation``) is intentionally NOT exercised
here — that needs a real ``Job``/``JobTranslation`` DB round-trip and belongs
in a service-layer integration test, not this offline prompt/safety eval.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from typing import Any
from unittest import mock

from app.ai.evaluation.models import Probe
from app.modules.opportunities.application import translation_service as svc


class _FakeCompletion:
    def __init__(self, text: str) -> None:
        self.text = text


def _fake_runner_factory(
    *,
    response_text: str | None = None,
    raise_error: BaseException | None = None,
):
    class _FakeRunner:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def complete(self, *_args: Any, **_kwargs: Any) -> _FakeCompletion:
            if raise_error is not None:
                raise raise_error
            return _FakeCompletion(response_text or "{}")

    return _FakeRunner


async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}
    job = SimpleNamespace(
        id=uuid.uuid4(),
        language_code=inp.get("source_lang", "en"),
        title=inp.get("title", ""),
        description=inp.get("description", ""),
        requirements=inp.get("requirements"),
        benefits=inp.get("benefits"),
    )
    target_lang = inp.get("target_lang", "vi")
    machine_draft = inp.get("machine_draft")

    mode = inp.get("provider")
    raise_error: BaseException | None = None
    response_text = "{}"
    if mode == "unavailable":
        from app.shared.exceptions import AIUnavailableError

        raise_error = AIUnavailableError()
    elif mode == "bad_json":
        response_text = "this is not valid json at all"
    elif mode == "unexpected_error":
        raise_error = RuntimeError("simulated unexpected provider error")
    elif inp.get("raw_response_text") is not None:
        # Direct control over the raw model text — used to test fence-stripping
        # and non-dict-JSON degrade paths that a plain llm_json dict can't express.
        response_text = inp["raw_response_text"]
    else:
        llm_json = inp.get("llm_json")
        if llm_json is not None:
            response_text = json.dumps(llm_json, ensure_ascii=False)

    async def _fake_machine_translate(*_args: Any, **_kwargs: Any) -> dict | None:
        return machine_draft

    with (
        mock.patch.object(svc, "_machine_translate_job", new=_fake_machine_translate),
        mock.patch.object(
            svc,
            "AiTaskRunner",
            _fake_runner_factory(response_text=response_text, raise_error=raise_error),
        ),
    ):
        try:
            result = await svc._ai_translate(job, target_lang=target_lang, session=None)
        except Exception as exc:  # defensive — _ai_translate should never raise
            return Probe(
                kind="jd_translation",
                raised_code=getattr(exc, "code", None),
                raised_message=str(exc),
            )

    blob = json.dumps(result, ensure_ascii=False, default=str).lower()
    return Probe(kind="jd_translation", blob=blob, data={"result": result})


def check(key: str, exp: Any, probe: Probe) -> str | None:
    """Assertion checks for ``jd_translation`` probes."""
    if key == "no_stack_trace":
        bad = "traceback" in probe.raised_message.lower()
        return "stack trace leaked in error message" if bad else None
    if key == "no_crash":
        return None

    result = (probe.data or {}).get("result")
    if key == "result_is_none":
        got = result is None
        return None if got == bool(exp) else f"result_is_none expected {exp}, got {got}"
    if key == "field_equals":
        if result is None:
            return f"expected a result dict to check {exp!r}, got None"
        field = exp.get("field")
        want = exp.get("value")
        got = result.get(field)
        return None if got == want else f"{field} expected {want!r}, got {got!r}"
    if key == "field_is_none":
        if result is None:
            return None  # whole result is None — trivially "field is None" too
        got = result.get(exp) is None
        return None if got else f"{exp} expected None, got {result.get(exp)!r}"
    if key == "blob_excludes":
        return None if str(exp).lower() not in probe.blob else f"result should exclude {exp!r}"
    if key == "blob_contains":
        return None if str(exp).lower() in probe.blob else f"result should contain {exp!r}"
    return None  # unknown / informational key
