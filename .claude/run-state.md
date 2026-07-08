# Autopilot Run State — ACTIVE CACHE

> Keep this file under 250 lines. Historical details live in `docs/IMPLEMENTATION_STATUS.md`.

## Speed Rules
- 1-3 localized files → `/tiny-patch` behavior (no docs, no subagents, cheapest check).
- Build batches → main conversation; subagents only for independent review/risk.
- Check this file first before reading long docs.

## Design Tokens Quick Reference
Aurora shell (v6.2):
```css
background: radial-gradient(ellipse 90% 60% at 10% 10%, rgba(147,197,253,0.72) 0%, transparent 55%),
  radial-gradient(ellipse 65% 48% at 92% 5%, rgba(196,181,253,0.60) 0%, transparent 50%),
  radial-gradient(ellipse 58% 70% at 50% 100%, rgba(110,231,183,0.48) 0%, transparent 60%),
  #EEF4FF
```
Glass tokens: card `border border-white/60 bg-white/82 backdrop-blur-md`
AI panel: `border border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white/60`

## AI System Status — CHECKPOINT GREEN (2026-07-01 updated)

### Gateway & Providers
- OpenAI-compatible provider via OpenRouter (confirmed working with real key)
- Aliases: chat_cheap→deepseek-chat, reasoning_cheap→deepseek-r1, embedding_cheap→text-embedding-3-small
- chat_free→deepseek-chat (ultra-cheap), chat_mini→meta-llama/llama-3.1-8b-instruct
- AI_REAL_CALLS_ENABLED=true in backend/.env (free alias set as default for local dev)
- AI_DEFAULT_MODEL_ALIAS=chat_free (backend/.env)
- Added HTTP-Referer and X-Title headers to all gateway calls (OpenRouter routing fix)

### Safety Layer
- input_guard.py: PII redaction added (email, phone VN, CCCD 9/12 digits, long numbers)
- input_guard.py: PII redacted BEFORE injection check
- output_guard.py: added _TOKEN_FIELD_RE to scrub prompt_tokens/completion_tokens field names
- output_guard.py in safety/: also has guard_completion (string-based, different from gateway version)

### Term Expansion Fix (CRITICAL)
- FIXED bidirectional expansion bug: python→fastapi caused FastAPI to be "matched" when CV had Python
- Now "python" expands only to abbreviations (py, python3) — NOT to frameworks
- Frameworks (fastapi, django, flask, react, etc.) have SEPARATE entries with only spelling variants
- k8s↔kubernetes still bidirectional (correct — same technology, different spellings)
- VERIFIED: "Python only" CV → FastAPI is correctly a GAP; k8s↔kubernetes still works
- Offline eval: 11/11 recommend_cv_for_job (was 10/11 before fix)

### Retrieval & RAG
- Hybrid search (BM25 + pgvector RRF) exists in retrieval/hybrid_search.py
- Reranker (LLM listwise) in retrieval/rerank.py — NOW WIRED into recommend_jobs tool
- recommend_jobs now: hybrid_search(limit×3) → rerank_jobs → fetch details → return
- job_embeddings table: migration 0039 (pgvector with IVFFlat index)

### Chatbot Tools (22 total)
- 20 original + 2 new: start_interview_sim (read_only), save_job (confirmation_required)
- start_interview_sim: generates real AI question or deterministic fallback when offline
- save_job: requires confirmation before executing, calls saved_job_service
- Tool RBAC enforced per tool spec (get_skill_gap: student/alumni only)

### Observability & Cost Tracking
- ai_usage_log table: migration 0040 (UUID PK, task_type, model_alias, success, char buckets, cost_usd)
- ORM model: app/ai/observability/models.py (AiUsageLog)
- Async DB writer: log_ai_usage_async() in usage.py — never raises, wraps in try/except
- Sync logger: log_ai_usage() unchanged (used in tests and sync contexts)

### Evaluation Datasets
- cv_ai_suggestions: 5 categories (10/5/5/5/3 cases) — PASS
- recommend_cv_for_job: 5 categories (11/5/5/5/3 cases) — PASS (was 10/11 before fix)
- interview_sim: 5 categories (10/5/5/5/3 cases) — eval runner not yet wired in run_eval.py
- run_eval.py: ALL 3 families wired (cv_ai_suggestions + recommend_cv_for_job + interview_sim) — PASS

### Eval Gate Fixes (2026-07-01 continued)
- factory.py `_get_api_key`: uses `get_settings().openrouter_api_key` (pydantic-settings reads .env) instead of raw os.environ
- input_guard.py: `sk-[A-Za-z0-9_\-]{8,}` PII pattern added first in _PII_PATTERNS list (catches API keys)
- run_eval.py `run()`: patches `real_provider_active=False` for the entire eval so offline behavior is guaranteed
- ALL 3 eval families now pass: 100% across 5 categories each

### Job-Fit AI Explanation
- ALREADY IMPLEMENTED in job_fit_service.py _maybe_explain() → generate_note()
- Gated on: real_provider_active() AND job_fit_ai_explanation_enabled flag
- Now works with AI_REAL_CALLS_ENABLED=true

## AI Smoke Tests — ALL GREEN (2026-07-01)

Offline eval: PASS (2/2 families, all categories)
Real-call smoke (10/10 PASS, used 8 actual API calls total ~$0.0001):
- pii_redact_email_phone_cccd ✅
- pii_redact_before_injection_check ✅
- fastapi_is_gap_when_cv_has_python_only ✅
- k8s_matches_kubernetes ✅
- job_fit_scoring_correct (matched=['Python'] gaps=['FastAPI','Kubernetes']) ✅
- provider_active ✅
- basic_chat (English) ✅
- vietnamese_reply ✅
- interview_sim_question ✅
- output_guard_scrubs_provider_and_tokens ✅

TypeScript build: 0 errors.

## Files Changed This Session (AI Upgrade Batch 2)
- `backend/.env` — AI_REAL_CALLS_ENABLED=true, AI_DEFAULT_MODEL_ALIAS=chat_free
- `backend/app/ai/gateway/openai_compatible.py` — added chat_free/chat_mini aliases, HTTP-Referer/X-Title headers
- `backend/app/ai/gateway/output_guard.py` — _TOKEN_FIELD_RE for prompt_tokens/completion_tokens
- `backend/app/ai/safety/input_guard.py` — PII redaction (_PII_PATTERNS), redact_pii(), sanitize_instruction/notes updated
- `backend/app/ai/cv/term_expansion.py` — major restructure: frameworks separated from language abbrevs, bidirectional bug fixed
- `backend/app/ai/retrieval/rerank.py` — (already existed, just confirming it's wired)
- `backend/app/modules/ai_assistant/application/tool_registry.py` — reranker wired in recommend_jobs, start_interview_sim tool, save_job tool, dispatch handlers
- `backend/app/ai/observability/models.py` — AiUsageLog ORM model (NEW via subagent)
- `backend/alembic/versions/0040_ai_usage_log.py` — migration (NEW via subagent)
- `backend/app/ai/observability/usage.py` — log_ai_usage_async() added (via subagent)
- `backend/app/ai/evaluation/datasets/interview_sim/` — 5 dataset files (NEW)

### Admin AI Provider Manager UI (2026-07-01) — DONE
- `frontend/src/lib/api/ai-settings.ts`: added AiProvider, AiModelAliasRow types + aiProvidersApi + aiAliasesApi
- `frontend/src/lib/api/index.ts`: exported new types and API objects
- `frontend/src/components/ai-settings/ai-provider-manager.tsx`: NEW — ProvidersSection + AliasesSection + AiProviderManager
  - Add/edit providers: name, type, base_url, description; toggle is_active; key indicator (presence only)
  - Add/edit aliases: alias_name, model_id (internal), provider_id, task_families, description; toggle is_active
  - Security note: model_id shown in CREATE form only (admin-only surface), never in LIST; built-in badge on seeded rows
- `frontend/src/components/ai-settings/ai-settings-screen.tsx`: AiProviderManager injected below budget section
- TypeScript build: 0 errors. Next.js build: clean. Eval gate: OVERALL PASS.

## AI Governance Upgrade — CHECKPOINT GREEN (2026-07-01 continued)

### P0 fixes — ALL DONE
- `tests/conftest.py`: Added AI_DEFAULT_MODEL_ALIAS=chat_cheap, AI_REASONING_MODEL_ALIAS, AI_EMBEDDING_MODEL_ALIAS, AI_EVAL_MODEL_ALIAS, AI_DAILY_COST_LIMIT_USD, CV_LLM_STRUCTURING_ENABLED overrides — previously failing test now passes
- `chat_service.py stream_message()`: Replaced `_stream_tokens()` (which called provider.stream() again) with `_local_stream_chunks()` — local word-by-word yield from final_text, zero second LLM call
- `budget_guard.py`: Added real `check_async(db, alias, estimated_cost_usd)` — queries `ai_usage_log.cost_usd` for today's spend, raises 402 when budget exceeded. `check()` sync path wired to SpendAccumulator protocol.

### P1 architecture — ALL DONE
- `app/ai/gateway/task_runner.py` (NEW): Unified `AiTaskRunner` class — single pipeline for budget check, policy orchestration, provider routing (with circuit breaker), output guard, cost logging, eval sampling. All domain modules should call this instead of provider.complete() directly.
- `app/ai/safety/policy_orchestrator.py` (NEW): Structured safety pipeline — intent classification (harmful, boundary_probe, off_topic, competitor, personal_data) BEFORE sanitise_instruction, then policy decision (allow/allow_with_note/rewrite/refuse). Tool permission class gates (read_only/write_with_confirm/admin_only). Audit log metadata only.
- `app/ai/observability/cost_estimator.py` (NEW): Per-alias cost estimates in USD/1M tokens, char-to-token proxy, conservative default for unknown aliases.
- `app/ai/extraction/adapters/ocr.py`: Fixed PDF OCR — `_recognize_pdf()` rasterizes pages with fitz/PyMuPDF at 200dpi before Tesseract; previous `Image.open(pdf_bytes)` produced blank/error results.
- `tool_registry.py _start_interview_sim()`: Now uses AiTaskRunner (alias from runtime_config, task_type="interview_sim") — no more hard-coded alias="chat_cheap" + get_provider() bypass.
- `translation_service.py _ai_translate()`: Now uses AiTaskRunner (alias from runtime_config, task_type="jd_translation") — no more alias="chat_cheap" + get_provider() bypass.
- `chat_service.py _llm_complete()`: Budget pre-check via check_async before provider call, cost_usd written on every log entry.

### Tests added
- `tests/unit/test_ai_governance.py` (NEW): 12 tests — cost estimator, policy orchestrator (benign/harmful/boundary/PII/competitor/tool_class), budget guard sync accumulator.
- All 50 AI tests pass (22+12+3+3+10).

## DB / Structure Batch — CHECKPOINT GREEN (2026-07-01)

### tool_registry.py split — DONE
- `tool_registry.py`: 1,660 → 17 lines (re-export facade only)
- `tools/__init__.py`: public API (ToolSpec, TOOL_SPECS, dispatch_tool)
- `tools/specs.py`: 24 ToolSpec declarations (477 lines)
- `tools/dispatch.py`: async router, maps names to handlers (89 lines)
- `tools/jobs.py`: 8 job handlers (255 lines)
- `tools/events.py`: 3 event handlers (83 lines)
- `tools/student.py`: 3 student handlers (84 lines)
- `tools/companies.py`: 3 company handlers (94 lines)
- `tools/partner.py`: 1 partner handler (38 lines)
- `tools/cv_ai.py`: 5 CV/AI handlers + career data (326 lines)
- `tools/kb.py`: 1 RAG handler (54 lines)
- 157/158 unit tests pass (1 pre-existing ja/zh language detection)

### knowledge_base module — DONE
- Migration 0043: knowledge_bases + knowledge_base_documents + knowledge_base_chunks
- `knowledge_base/domain/models.py`: fixed wrong `from app.db.base import Base` → `from app.shared.models`
- `knowledge_base/api/router.py` (NEW): CRUD + upload + RAG query endpoints
- `bootstrap/routes.py`: KB router mounted at `/api/v1/knowledge-bases`
- OpenAPI: 4 KB paths confirmed

### Scalar API docs — DONE
- `scalar-fastapi==1.8.2` installed
- `main.py`: Scalar mounted at `/api/scalar`, Swagger disabled, 23 tag groups, Vietnamese description
- `openapi_url=/api/openapi.json`

## Next Batch Candidates (priority order)
1. **CV Ingestion flow** — preview-first upload, extraction review beside original (priority: core student workflow)
2. **Student CV dashboard visual polish** — cv-builder-screen, job-fit rail
3. **Public homepage** — partner banner, curated spotlight quality
4. **platform_feedback service** — module has models + router but no application/ layer
