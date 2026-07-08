# ADR-0016 — AI Mock Interview (realtime-capable, JD+CV grounded)

Status: Accepted — 2026-07-09
Module: `backend/app/modules/mock_interview` · Frontend `/[locale]/jobs/[id]/interview`

## Context

Students need realistic interview practice on a specific job: an HR-style
interviewer that asks specialized questions grounded in BOTH the job's JD AND the
student's chosen CV (probing real CV items against real JD requirements, with
natural follow-ups), gives coaching — **no scoring** — and stores transcripts the
student can review. University staff must be able to govern/monitor the feature
(aggregate stats, safety-flag counts, config); partners have no access;
platform/AI-ops need to read content to debug AI quality without violating
student privacy. The experience should feel like a live spoken conversation while
staying cheap and provider-agnostic.

## Decision

### 1. Separate the "brain" from the "shell"
The interviewer reasoning + the post-session coaching report run **text→text
through the existing safe gateway** (`AiTaskRunner`): budget/policy guards, output
scrubbing, PII-safe usage logging, telemetry, and 1% eval sampling to
`ai_eval_samples`. The realtime **voice** path is a thin I/O shell that never
carries model reasoning. This keeps every governance/observability guarantee that
already applies to AI text, and makes the feature fully testable offline.

### 2. Three delivery tiers (one contract)
- **V1 — browser-native voice (default, runs on OpenRouter today):** browser STT
  (`SpeechRecognition`) + TTS (`speechSynthesis`) drive the text brain over an SSE
  turn endpoint. Spoken interview at ~zero extra provider cost.
- **V2 — true realtime speech-to-speech (superadmin-activatable):** a
  provider-agnostic registry (`app/ai/gateway/realtime/`) mints a short-lived
  **ephemeral** token so the browser connects DIRECTLY to a native provider
  (Gemini Live / OpenAI Realtime); audio never transits our servers. **Disabled by
  default** — OpenRouter is text-only and cannot proxy realtime audio. Until a
  native ephemeral mint is wired + verified, the mint raises and the feature falls
  back to V1; it **never** returns a raw provider key to the client.
- **T — text:** typed fallback / accessibility floor over the same turn endpoint.

The interview brain model is a leak-safe alias `interview_default`
(`ai_interview_model`, default `google/gemini-2.5-flash` on OpenRouter — fast,
Vietnamese-capable, cheap; swappable by a superadmin without code changes).

### 3. New module, isolated from `recruitment`
`mock_interview` follows `api/application/domain/infrastructure`. Tables
`mock_interview_sessions` / `mock_interview_turns` (migration `0084`) are separate
from `recruitment.interviews`; the feature key/task types (`mock_interview_turn`,
`mock_interview_report`, `mock_interview_realtime`) are separate from the older
ephemeral `interview_sim` / `answer_feedback`. Grounding is composed over PUBLIC
read models only — `opportunities.job_fit_read.load_job_for_fit` and a new
documents-owned `interview_grounding_service` — so no cross-module implementation
imports. The frozen grounding is stored on the session for a stable interview.

### 4. No scoring; coaching only
The report normalizer copies only whitelisted coaching fields
(`per_question[{question,suggestion,observation}]`, `overall_observations`,
`gaps_to_work_on`, `strengths`); any `score`/`rating`/`grade` the model emits is
dropped by omission. Static, gap-keyed fallback on any AI failure.

### 5. Cost control (layered)
Ephemeral-token TTL (provider-enforced, V2) + 10-min session cap + question cap +
1 concurrent session + idle auto-end + per-user daily (3) / weekly (10) session
caps + the shared weekly `ai_usage_log` quota. Grounding is injected once.

### 6. Governance vs observability (privacy boundary)
- **University (masked, aggregate):** RBAC noun `mock_interview:{read,manage}`
  gated by the `org_type=="university"` pattern (partner `*:*` cannot pass).
  Reads aggregate analytics events (`mock_interview.started/completed/flagged`,
  aggregate type `mock_interview_session`) + safety-flag counts. **No named
  transcripts.**
- **Superadmin / AI-ops (content, controlled):** report auto-samples to
  `ai_eval_samples` (pseudonymized via `redact_pii`); safety-flagged sessions
  escalate to the moderation queue (`source="mock_interview_safety"`, metadata
  only); full-transcript view is superadmin-only, **audited on every open**
  (`mock_interview.transcript_viewed`) and available for a session only when the
  student has opted in via the existing `interview_recording` consent.
- **Partner:** no route, facade, or permission.

Every session/turn query is hard-scoped to the owner; all writes are audited;
presenters strip `provider_ref`/`model_ref`/`grounding_json`/`text_redacted`.
Transcripts are TEXT ONLY — audio is never persisted.

## Consequences
- Students get a spoken, JD+CV-grounded practice interview today on OpenRouter;
  true low-latency speech-to-speech is a superadmin config away (native key).
- The feature inherits all existing AI safety/observability rails for free.
- Deferred: the per-university enable/quota config store (V1 uses global
  `feature_flags` + code caps) and the AI-ops `ai_eval_samples` reviewer UI.

## Update — 2026-07-09 (realtime wired + adaptive + analytics)

- **Realtime V2 is now implemented, not just scaffolded.** `GeminiLiveProvider`
  mints a Gemini Live ephemeral token via `POST /v1alpha/auth_tokens` with
  `bidiGenerateContentSetup` constraints (model + system instruction locked
  server-side; request format verified against Google's live endpoint). Reads
  `GEMINI_API_KEY`; default model `gemini-2.5-flash-preview-native-audio-dialog`.
  Missing/invalid key → graceful fallback to browser-voice. Frontend
  `gemini-live-client.ts` streams mic PCM16@16kHz ⇄ plays PCM16@24kHz with
  barge-in and maps input/output transcription to stored turns. Status: API
  wired; browser-verify with a real key + mic.
- **Auto-adaptive interview (no manual mode picker).** `grounding_service`
  deterministically infers `focus` (technical/behavioral/mixed) + `difficulty`
  (foundational/intermediate/advanced) from the JD; the interviewer prompt adapts
  and runs natural phases. The CV-JD match drives the interview, not a form.
- **Student progress** (`GET /mock-interview/progress`): recurring coaching
  themes (gaps + strengths, with counts) + focus mix across completed sessions —
  the score-free progress signal. Frontend adds a progress summary, "practice
  again", and PDF export of the coaching report.
- **Deeper university analytics**: per-day trend, most-practiced jobs, and focus
  mix added to the aggregate stats (still PII-free) with monochrome charts.
