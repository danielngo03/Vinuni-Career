# Partner Chatbot — Processing Layers & Eval Coverage Gap Analysis

Author: AI-engineer (EVAL lane, Wave-2). Scope: the partner recruiter chatbot
(`ai_assistant`) as it exists on `feat/partner-ai-power`. This is an honest
engineer's map — what each processing layer actually does today, where it is
thin or missing, and a concrete next step. It then maps eval/dataset coverage
and gives a prioritized robustness backlog. Everything below is file-referenced.

Verification basis: offline seam probes + the new `partner_golden` benchmark
(34 conversations / 199 per-turn checks, all green). No provider/model/token
internal is exposed in any layer's user-facing output — confirmed by the
leak-guard on every golden conversation.

---

## 1. Processing layers (request → response)

A partner turn flows: **input guard → policy → router/tiering → tool-subset →
native tool loop (RBAC + confirmation) → output guard → scope/leak guard →
memory → telemetry → energy metering → status phases → grounding**. Per layer:

### 1.1 Input guard — `app/ai/safety/input_guard.py`
- **Exists:** Fast regex sanitisation — PII redaction (phone/email/CCCD),
  injection-marker stripping on the user message. **NEW (landed this wave):**
  `neutralize_untrusted_text` / `neutralize_tool_payload` defuse EN+VI
  instruction-injection markers embedded in DATA the assistant reads back (a
  candidate CV/headline, an uploaded attachment's extracted text, a KB chunk),
  replacing each marker with `[removed]` while preserving benign data and
  non-string scalars; `native_loop` records an `untrusted_data_neutralized`
  guard flag when it fires. Covered end-to-end by the new
  **`partner_tool_injection`** eval family (29 checks) and the benchmark
  `injection_defense` seam sweep.
- **Weak/missing:** `neutralize_tool_payload` is wired into `native_loop`'s
  tool-result path; the **attachment-extraction path** (`attachment_service`)
  and any KB retrieval that bypasses the tool loop still need the same
  `neutralize_untrusted_text` pass at ingest. Neutralization is marker-based
  (denylist), so novel obfuscations can slip.
- **Recommendation (P1, downgraded from P0):** Route every attachment excerpt
  through `neutralize_untrusted_text` at extraction time (not only tool
  results), and add an embedding/heuristic backstop for obfuscated markers.

### 1.2 Policy orchestrator — `app/ai/safety/policy_orchestrator.py`
- **Exists:** Strong. Intent classification (harmful / boundary-probe /
  off-topic / external-source / benign) → action (allow / allow_with_note /
  rewrite / refuse), tool-class-aware. Bilingual vi+en model-probe, system-prompt
  reveal, jailbreak, and external-web patterns; refusals never reach a model.
  Golden adversarial set (6 journeys) is 100% green including tight vi brand
  probes ("Bạn là GPT hay Gemini?") and vi/en injection.
- **Weak/missing:** Pattern-based, so novel obfuscations (unicode homoglyphs,
  base64, "spell it backwards") can slip. No semantic/embedding fallback for
  probe detection. `allow_with_note` path is under-exercised in eval.
- **Recommendation (P1):** Add a cheap embedding-similarity backstop for
  boundary-probe intents (compare to a curated probe-centroid set) as a second
  opinion when regex is silent but the turn scores high on meta/system tokens.

### 1.3 Model router / tiering — `app/modules/ai_assistant/application/model_router.py`
- **Exists:** Deterministic (no routing-LLM) 3-tier router: `cheap` for
  greetings/meta, `default` for operational asks, `reasoning` only for explicit
  deep-analysis. Keyword→group signals map to 8 tool intent groups. **Fail-open**
  is correct — an ambiguous turn returns `confident=False` and `select_specs`
  hands back the FULL tool set (golden `pg_lq_ambiguous_failopen_vi`,
  `pg_lq_short_bare_number_vi`). Aliases never leave this layer.
- **Weak/missing:** Purely lexical. "How many new applications this week?" only
  routes to `pipeline` if it contains an exact signal substring; near-miss
  phrasings fall to `cheap` + full-toolset (safe but pays the full-schema token
  cost the router exists to avoid). No confidence *score*, only a boolean.
- **Recommendation (P1):** Add an embedding-nearest-group tiebreak when zero
  keyword groups match but the turn is clearly operational (length + verb), so
  the token-saving subset fires more often without losing fail-open safety.

### 1.4 Tool-subset selection — `model_router.select_specs`
- **Exists:** Union of matched groups + always-on `core`; tolerates
  not-yet-registered group members; empty subset → full set. Golden
  `route_selects_full_set` checks lock the fail-open contract.
- **Weak/missing:** The saving is only realised if the caller actually passes
  the subset to the provider; there is no eval that the LIVE turn advertised the
  reduced `tools=` array (offline can only prove the pure function). No metric on
  average tokens saved per turn.
- **Recommendation (P2):** Emit a telemetry counter `tools_advertised` per turn
  so the token-savings claim is measurable, and add one real-mode assertion that
  a greeting turn advertises ≤ core-group size.

### 1.5 Native tool loop — RBAC + confirmation — `native_loop.py`, `tool_loop.py`
- **Exists:** Best-in-class seam. `authorize_tool` + `available_specs` gate every
  tool by persona AND real `permission_checker` grants (org/dept scoped), so the
  chatbot can never exceed the human's reach — golden privacy set proves
  exporter≠admin, jobs-read≠export, student sees zero partner tools, guest sees
  zero tools. `confirmation_required` tools (`create_job`, `move_candidate_stage`,
  `apply_job`, `save_job`) are never executed inline; a pending confirmation card
  is persisted. Dispatch re-checks RBAC (defense in depth). `MAX_ITERATIONS=8`,
  `MAX_TOOL_CALLS_PER_TURN=12` respected.
- **Weak/missing:** Tool RESULTS are truncated to 6000 chars but not
  guard-scanned (see 1.1). No per-tool circuit breaker for a tool that errors
  repeatedly inside one turn (it just consumes iterations). Cross-org safety is
  structural (tools carry NO `org_id`/`company_id` param — golden
  `pg_priv_cross_org_no_org_param`) but there is no explicit test that a tool
  IMPLEMENTATION rejects a spoofed org in its own query.
- **Recommendation (P1):** Add a per-turn tool error budget (e.g. abort after 2
  consecutive tool failures with a safe degradation) and a service-layer test
  that each partner tool query filters by `principal.org_id`.

### 1.6 Output guard — `app/ai/gateway/output_guard.py`
- **Exists:** `scrub_text` / `guard_completion` strip provider names, model ids,
  aliases, token counts, `sk-` keys, storage paths. Applied to judge output,
  memory summaries, titles, and (must be) every streamed chunk. Golden fallback
  set + the leak-guard on all 34 conversations are green.
- **Weak/missing:** Scrubbing is a denylist of known terms
  (`leak_checks.FORBIDDEN_TERMS`). A new provider/model codename not in the list
  would pass. No structural check that streamed deltas are scrubbed (only the
  terminal message is easy to test offline).
- **Recommendation (P1):** Add a generic "looks like a model id" heuristic
  (`vendor/name-version` slug shape) to the scrubber, and a real-mode assertion
  that a model-probe turn's *streamed* answer is leak-free chunk-by-chunk.

### 1.7 Scope / leak guard (persona exposure) — `native_loop._persona_token`, `messages.py`
- **Exists:** Persona mapping keeps university/student/partner tool universes
  disjoint; user-facing copy is i18n via `assistant_message` (no raw enum/status).
- **Weak/missing:** No single "scope guard" module — scope is enforced implicitly
  across router + native_loop + policy. Off-domain asks (a partner asking the bot
  to write their thesis) route to `cheap` and answer generically rather than
  redirecting to product scope.
- **Recommendation (P2):** A light off-domain nudge ("I help with your
  recruiting workflow — here's what I can do") when intent is benign but matches
  no tool group and no product topic.

### 1.8 Conversation memory — `session_history.py`
- **Exists:** Rolling summary (`update_session_memory`, `_summarize_history`),
  stale-memory reset on edit/regenerate (`_reset_memory_if_stale`), output-guard
  scrubbed, cap-bounded (tail-kept). Deterministic offline (truncated
  concatenation) so it is testable — golden `pg_hp_memory_recall_vi` proves an
  anchor ("Data Analyst") survives across 3 turns.
- **Weak/missing:** Summary is lossy truncation offline and a single cheap-model
  pass online — no structured "facts" memory (which job, which candidate, which
  filter the recruiter is working on). Cross-turn ENTITY carryover (the model
  re-asking "which job?") is not guaranteed.
- **Recommendation (P1):** Add a small structured working-memory slot
  (active_job_id / active_stage / last_export) updated from tool calls, injected
  as facts, so follow-ups resolve pronouns deterministically.

### 1.9 Telemetry — `turn_telemetry.py`, `app/ai/observability/`
- **Exists:** `_usage_context` builds a `UsageContext`; provider/model resolved
  internally for the ledger only (never surfaced). Spans/usage logged.
- **Weak/missing:** No per-layer span (policy_ms / route_tier / tools_advertised
  / tool_calls / escalated) surfaced to observability, so we cannot yet chart
  tier mix or escalation rate. Grounding/quality is not logged per turn.
- **Recommendation (P1):** Emit structured, leak-safe turn attributes
  (tier, groups_matched, tools_advertised, tool_calls, confirmations,
  escalated, refused) to feed the eval/ops dashboards.

### 1.10 Energy metering / quota — `usage_service.enforce_quota`, `app/ai/observability/usage.py`
- **Exists:** `send_message` enforces daily+weekly allowance before any model
  call, refuses with a safe `QUOTA_EXCEEDED` (golden `pg_fb_quota_exhaustion_vi`
  proves the message is leak-safe and carries no `409`/internal code). Durable
  usage ledger + `log_ai_usage`.
- **Weak/missing:** Metering is per-turn allowance, not per-*model-call* cost —
  a heavy reasoning turn with many tool calls counts the same as a greeting.
  No idempotency key on the ledger write per turn visible at this layer.
- **Recommendation (P2):** Weight allowance by tier (reasoning > default >
  cheap) and add a turn-scoped idempotency key so a retried turn is not
  double-charged.

### 1.11 Status phases (streaming) — `chat_service.py`
- **Exists:** SSE `status` events are emitted during streaming (e.g.
  `retrieving_context`).
- **Weak/missing:** There is **no leak-safe phase-mapping helper** exposing the
  full documented vocabulary (understanding | retrieving | analyzing | drafting |
  visualizing | exporting | generating_image | composing). `partner_golden`
  ships the intended taxonomy (`PHASE_BY_ARTIFACT` in
  `runners/partner_golden.py`) and imports a live helper **defensively** — its
  absence is surfaced as a pending integration item, never a failure. So the
  golden set pins the phase a turn SHOULD surface, but the backend does not yet
  emit that exact vocabulary from a single testable function.
- **Recommendation (P1):** Land `phase_for_intent(tool_or_group) -> str` in the
  streaming lane returning exactly this vocabulary; the golden `phase` checks
  turn strict automatically (the runner already looks for it).

### 1.12 Grounding — `citation_verify.verify_citations`, `guardrails.has_ungrounded_numeric_claim`
- **Exists:** Two real, deterministic grounding seams. (a) `verify_citations`
  (§6.5) strips any `Theo <Doc>` / `According to <Doc>` citation that names a
  document not actually retrieved this turn — the new **`partner_rag`** family
  (28 checks) locks grounded-kept / fabricated-stripped / audience-isolation /
  refuse-when-insufficient. (b) **NEW:** `has_ungrounded_numeric_claim` is a
  conservative telemetry detector that flags a recruiting count/%/salary asserted
  with no tool this turn — exercised by the `partner_chat` `ungrounded_numeric`
  adversarial cases and the benchmark `grounding` seam sweep. The judge rubric
  still scores grounding end-to-end in the `--real` batch.
- **Weak/missing:** `has_ungrounded_numeric_claim` is a **telemetry flag only**
  — it never mutates or regenerates the answer, and it does not verify that a
  cited figure equals the tool value (only that a figure exists without a tool).
  There is no runtime verify-then-regenerate loop.
- **Recommendation (P1):** Promote the detector into a post-generation pass that,
  on a flagged ungrounded figure, appends a grounded-source disclaimer or
  triggers one regeneration with the tool data re-injected.

---

## 2. Dataset / eval coverage map

### 2.1 Task families that exist (offline gate, `run_eval`)
26 families ship 5-category datasets (10/5/5/5/3 minimums), all green offline:
`cv_ai_suggestions, cv_edit_command, recommend_cv_for_job, interview_sim,
ai_assistant_chat, jd_generation, jd_extraction, knowledge_base_query,
bias_detection, cover_letter, jd_translation, scorecard_suggest,
screening_brief, interview_prep, answer_feedback, competition_signal_explanation,
content_moderation, fraud_detection, market_intelligence, mock_interview_report,
talent_match, partner_jd_builder`, plus the partner power-up families added by
this lane:
- **`partner_chat`** — GROWN to 37/16/18/15/12 (was 19/8/9/7/6): more realistic
  recruiter asks + an `ungrounded_numeric` adversarial case, cross-org data
  request, vi+en model probes, export applicants-vs-jobs disambiguation.
- **`partner_golden`** — 34 curated multi-turn conversations (199 per-turn checks).
- **`partner_tool_injection`** — 29 cases: tool-result / attachment / KB-chunk
  injection defense (`neutralize_*`) + RBAC scope-invariance under hostile content.
- **`partner_rag`** — 28 cases: KB citation grounding, fabricated-doc stripping,
  audience isolation, refuse-when-insufficient, chunk-injection defusing.

### 2.1a Robustness scoreboard (benchmark)
`benchmark_partner_chat` now rolls every offline assertion into a 0-100
robustness score with a per-layer breakdown across the four case-level partner
families + golden turns. Layers: **rbac, policy, injection_defense, grounding,
leak, artifact_correctness**. Current: **100/100** (≈796 checks) — the number
falls the moment any layer regresses, and the md+json report shows per-layer,
per-family, and per-category rates. This is a robustness scorecard; model answer
quality is the separate `--real` / `--real-golden` judge score.

### 2.2 Golden journeys shipped (this lane) — 34 conversations, 199 checks
- **happy_path (12):** pipeline→funnel chart, JD paste→draft→validate→create
  (confirm), export applicants-vs-jobs disambiguation, talent search by skills,
  upcoming events, image banner, analytics-conversion (reasoning tier),
  memory recall across turns, greeting→operational tier transition,
  scorecard→screening brief, JD bias check (scoped member), move-stage (confirm).
- **adversarial (6):** vi + en model probe, prompt injection, attachment-embedded
  injection, external web scrape, vi jailbreak/reveal-prompt.
- **privacy_boundary (6):** exporter denied talent CV search, jobs-read denied
  export, student blocked from partner tools, guest zero tools, cross-org
  structural impossibility (no org param), PII phone redacted before model.
- **low_quality_input (6):** ambiguous fail-open (full toolset), short bare ask,
  empty export args, wrong-type limit, missing required job_id, messy-but-pipeline.
- **fallback (4):** AI-unavailable vi/en, quota exhaustion, output-guard scrub.

### 2.3 What is thin / missing in coverage
- **Attachment / tool-result injection defense** — only demonstrated via the
  policy layer; there is no dataset that drives a poisoned tool RESULT back
  through the loop (blocked on the 1.1 wiring existing).
- **Escalation path** — no golden case asserts the one-step tier escalation when
  a cheap-tier completion is empty (needs a real-mode or a seam hook).
- **Multi-tool single turn** — golden asserts tool visibility/validation per
  turn, not a turn that legitimately chains 2–3 tools (funnel + export).
- **Streaming-chunk leak** — offline can only check the terminal text; no
  chunk-by-chunk leak assertion (needs real-mode).
- **`allow_with_note`** policy action — under-covered.
- **University-staff chatbot** — no equivalent golden set (out of this lane's
  scope but a clear next family: `university_golden`).

### 2.4 Golden cases to add next
1. `pg_adv_tool_result_injection` — a tool returns a candidate note containing
   "ignore instructions"; assert the inbound guard neutralises it (after 1.1).
2. `pg_hp_multi_tool_funnel_then_export` — one turn that legitimately needs
   funnel chart + export; assert both tools authorised + artifacts.
3. `pg_hp_escalation_on_empty_cheap` — cheap tier returns empty → exactly one
   escalation (real-mode / seam hook).
4. `pg_adv_obfuscated_probe` — homoglyph / reversed model probe (drives 1.2).
5. `pg_hp_entity_carryover` — "move him to interview" resolving `him` from the
   prior candidate turn (drives 1.8 working-memory).

---

## 3. Prioritized robustness backlog

### P0 — correctness/safety blockers
- **P0-1 Inbound-context injection defense (1.1/1.5). — LANDED (tool results).**
  `neutralize_tool_payload` now defuses injection in tool results inside
  `native_loop` (flagged `untrusted_data_neutralized`) and is gated by the
  `partner_tool_injection` family. **Remaining (P1):** extend the same
  `neutralize_untrusted_text` pass to the attachment-extraction ingest path and
  any non-tool-loop KB retrieval.
- **P0-2 Runtime numeric-grounding verifier (1.12). — PARTIAL.** The deterministic
  `has_ungrounded_numeric_claim` detector + `verify_citations` citation stripper
  both exist and are evaluated (`partner_chat` ungrounded_numeric, `partner_rag`).
  **Remaining (P1):** promote the detector from telemetry-only into a
  verify-then-annotate/regenerate pass over the final answer.

### P1 — high-value robustness / quality
- **P1-1 Online 1% sampling wired to chat.** `app/ai/observability/eval_samples.py::maybe_sample_async`
  exists but is wired only to `mock_interview/report_service.py` — **not** to the
  partner/student chat pipeline (`native_loop`/`chat_service`). Wire it so live
  chat answers flow to `ai_eval_samples` for async human review (AI_PRODUCT_SPEC
  §10.2). Cheap, high-leverage for continuous quality.
- **P1-2 Structured working memory (1.8).** active_job_id/active_stage/last_export
  slots for deterministic pronoun/entity carryover.
- **P1-3 Leak-safe phase helper (1.11).** Land `phase_for_intent()` returning the
  documented vocabulary; golden `phase` checks strict-activate automatically.
- **P1-4 Clarifying question on low-confidence intent (1.3).** Today a
  non-confident turn fails open to the full toolset and answers anyway; for
  genuinely ambiguous operational asks, prefer a single clarifying question over
  a guessed tool. `chat_service` has some clarify scaffolding to build on.
- **P1-5 Per-turn telemetry attributes (1.9)** for tier mix / escalation /
  tools-advertised dashboards.
- **P1-6 Embedding backstop for probe + routing (1.2/1.3).**

### P2 — efficiency / polish
- **P2-1 Semantic response cache.** Only `app/ai/retrieval/embeddings.py` caches
  today. A turn-level semantic cache (normalise + embed the turn, reuse a recent
  identical-intent answer within a session/org TTL) would cut tokens on repeated
  "pipeline?" style asks. Guard cache hits through the output guard.
- **P2-2 Tier-weighted metering + idempotency (1.10).**
- **P2-3 Off-domain scope nudge (1.7).**
- **P2-4 Multi-agent workforce for heavy analytics.** `app/ai/agents/workforce.py`
  exists (Celery dispatch); route `reasoning`-tier multi-metric analytics
  ("compare conversion across 4 quarters and 3 jobs") to a workforce plan
  instead of one long single-model turn.
- **P2-5 `tools_advertised` token-savings metric (1.4).**

---

## 4. How to run the golden benchmark

Offline (deterministic, CI-safe — 0 real calls):

    uv run python -m app.ai.evaluation.run_eval --task-family partner_golden
    uv run python -m app.ai.evaluation.benchmark_partner_chat            # golden section + seams

Real END-TO-END answer quality (opt-in; needs DB + a real provider; capped;
scores/flags only, no transcript). DO drive it only against a seeded verify
stack:

    AI_REAL_CALLS_ENABLED=true AI_MAX_REAL_CALLS_PER_TEST_RUN=6 \
      uv run python -m app.ai.evaluation.benchmark_partner_chat --real-golden \
      --real-principal partner_admin --max-real-cases 6

`--real-golden` drives each eligible golden conversation (those tagged with a
`real_rubric`) turn-by-turn through `chat_service.send_message` against the live
pipeline, then scores the final answer with `judge.judge_response`
(`partner_chat_answer` / `jd_draft_quality`). It refuses (exit 2, no report) unless
`AI_REAL_CALLS_ENABLED=true` and a real provider is active, and clamps to
`min(--max-real-cases, AI_MAX_REAL_CALLS_PER_TEST_RUN, 6)`. The orchestrator may
inject its own session factory / seeded-login principal via
`benchmark_partner_chat.run_real_golden_batch(session_factory=..., principal_name=...)`.
