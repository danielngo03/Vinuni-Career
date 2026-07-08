---
description: AI gateway, prompts, tool registry, extraction, matching, moderation, evaluation, and AI settings rules.
paths:
  - backend/app/ai/**
  - backend/app/modules/ai_assistant/**
  - backend/app/modules/ai_settings/**
  - backend/app/modules/knowledge_base/**
  - docs/AI_PRODUCT_SPEC.md
  - docs/SECURITY_PRIVACY.md
---

# AI Rules

Use for AI gateway, prompts, tool registry, assistants, extraction, matching, moderation, evaluation, and AI settings.

## Must Read

- `CLAUDE.md`
- `docs/AI_PRODUCT_SPEC.md`
- `docs/PRODUCT_REALITY_REBUILD_SPEC.md` for AI usefulness, confirmation,
  fallback, cost, privacy, and adjacent workflow checks
- `docs/PRODUCT_REQUIREMENTS.md` section 6
- `docs/CV_STUDIO_SPEC.md` for CV AI tasks
- `docs/BUSINESS_LOGIC.md` for touched features
- `docs/SECURITY_PRIVACY.md`
- `docs/API_CONTRACTS.md`
- `docs/ENVIRONMENT.md`
- `docs/LOCAL_DEV_STACK.md`
- `docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md` for AI-assisted communication drafts
- `docs/EDGE_CASES_FAILURE_MODES.md`
- `docs/SYSTEM_ACCEPTANCE_BAR.md`
- `docs/TEST_STRATEGY.md`

## Non-Negotiables

- Provider names, concrete model ids/model names, API keys, token counts,
  latency, raw confidence, prompt text, OCR internals, embedding internals,
  chunk IDs, similarity scores, and internal status codes are never exposed to
  guests, students, partners, ordinary university staff, exports, or
  notifications. Only platform superadmins may view or manage the real
  provider/model registry, and only in superadmin AI operations/settings
  surfaces. API keys and base URLs are never returned at any privilege level.
- AI write actions require explicit confirmation before execution (§4.3 confirmation protocol).
- AI decisions are advisory. Human final say on moderation, fraud, approvals, and consequential actions.
- Prompt templates are versioned under `backend/app/ai/prompts/{task}/v{N}.py` — owned by ai-engineer (§8.1).
- Prompt templates, system/developer/task instructions, and guardrail text must
  be written in English for consistency, portability, review, and eval reuse.
  User-facing output language is controlled by explicit `target_language`,
  detected CV language, or user locale; do not hardcode Vietnamese prompt
  instructions just because the default locale is `vi`.
- Tool registry (§7) must classify every tool with all required fields including fallback_behavior.
- All inputs pass through `input_guard.py` before LLM; all outputs pass through `output_guard.py` after LLM (§9).
- AI usage logs must NOT contain raw prompt content or chunk content — log metadata only (§15).
- Fallback behavior must be defined in tool registry and tested in eval dataset.
- All LLM calls go through AI gateway — no direct provider SDK calls in domain modules (§5).
- Unit tests use offline/fake providers; real calls are opt-in, capped, and low-cost/free aliases first (§18).
- Real AI smoke tests are allowed only after offline eval is green, with
  `AI_REAL_CALLS_ENABLED=true`, `AI_MAX_REAL_CALLS_PER_TEST_RUN` respected,
  cheap aliases only, and no raw prompt/PII/key/provider output in logs.
- CV/document extraction is a cost-tiered cascade: native text (free) -> local OCR
  -> a cheap vision-LLM for images and styled/scanned PDFs (owner-approved image
  path) -> optional text-LLM structuring. Escalate to a paid model only when the
  cheaper tier is insufficient; use the cheapest capable model (§19).
- The vision-LLM tier MAY receive DOWNSCALED document images (owner decision
  2026-07-05, supersedes the older "text-only to LLM" rule for the image/scanned
  path). The text-LLM structuring tier still receives extracted text only.
- Do not call any model for blank, corrupt, infected, password-protected, or
  not-CV uploads. The vision tier must return is_cv=false / no result for non-CVs;
  the cascade must NEVER fabricate a CV from a non-CV, blank, or junk file.
- Uploaded-CV extraction is backend-authoritative (owner decision 2026-07-05):
  there is no manual field-review step; the extracted, structured result is stored
  directly and feeds CV-JD matching, so it must be accurate and well-structured
  (group each job/degree into one coherent entry; capture skill/language
  proficiency levels shown as stars/bars/words).
- CV AI is CV-first: upload/template/raw-notes flows must work without a
  completed student profile form. Profile data is usable only as confirmed facts
  and preferences.
- CV-to-job recommendation returns a user-facing 0-100 product score with
  category explanation and evidence. It must not expose raw model confidence,
  embedding similarity, provider details, prompt text, or token metadata.
- Natural-language CV canvas edits must return a structured patch/diff against
  the selected CV version/element/section. They are confirmation-required and
  must never directly mutate CV content, layout, exports, or submitted
  application snapshots.
- Student competition intelligence must be deterministic/aggregate-first. AI may
  explain buckets in user-friendly language only after the backend produces
  privacy-safe signals. Never infer or expose exact applicant ranks, other
  candidates' identities, raw CV text, raw model confidence, provider/model,
  prompt, token, or cost internals.
- ReAct loop: MAX_ITERATIONS=8, MAX_TOOL_CALLS_PER_TURN=12 (§4.1).
- RAG must use hybrid search (dense + BM25 RRF) + cross-encoder reranking (§6.2-6.3).
- Cost tracking mandatory per request to `ai_usage_log` (§5.4).
- CV AI tools return pending diffs/drafts only and must not invent education, employers, GPA, awards, certifications, dates, language proficiency, work authorization, or quantified outcomes.

## Product Shape

- Use `ai_assistant` for chat/session/tool execution (module: `backend/app/modules/ai_assistant/`).
- Use `ai_settings` for AI governance (module: `backend/app/modules/ai_settings/`).
  Masked aliases/status/budget may be exposed to authorized university staff;
  real provider/model identity and provider/model CRUD are superadmin-only.
- Use `backend/app/ai/` for gateway, agents, extraction, matching, retrieval, safety, evaluation.
- Workforce/multi-agent tasks: `backend/app/ai/agents/workforce.py` dispatches to Celery workers (§4.2).
- Reranker: `backend/app/ai/retrieval/rerank.py` (§6.3).

## Evaluation Requirements

- Every shipped AI task has a eval dataset in 5 categories: happy_path, adversarial, privacy_boundary, low_quality_input, fallback (§10.1).
- Minimum 10 happy-path, 5 adversarial, 5 privacy, 5 low-quality, 3 fallback examples.
- Offline eval runs in CI — PR blocks on privacy boundary failures and < 80% happy-path pass rate.
- Rollback criteria must be defined before enabling any new AI feature (§17).
- Online: 1% sampling to `ai_eval_samples` for async human review (§10.2).

## Delivery Checklist

- Tool permission class and all registry fields documented (§7).
- Prompt path + version number documented; static prefix before dynamic content (§8.2).
- Confirmation card copy defined for mutating tools (§4.3).
- Input guard and output guard rules applied (§9).
- Provider leakage test in adversarial eval dataset.
- Eval dataset (5 categories) in `backend/app/ai/evaluation/datasets/{task_name}/`.
- Rollback criteria added to §17 or tool spec.
- Observability spans defined (§11.1).
- Cost estimate per request documented.
- Real-call smoke test count, alias, and cost estimate are reported when
  `AI_REAL_CALLS_ENABLED=true` without exposing the concrete provider/model id
  or API key.
- Validation failure gates are tested before model invocation.
