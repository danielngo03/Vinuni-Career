---
name: vinuni-ai-product
description: Use for AI product design, prompt/tool registry decisions, safety gates, evaluation, fallback, and rollback planning.
---

# VinUni AI Product Workflow

Use this skill for any feature involving model calls, prompts, agents, extraction, matching, moderation, RAG, AI settings, or AI-generated user output.

## Must Read

- `CLAUDE.md`
- `docs/AI_PRODUCT_SPEC.md`
- `docs/SECURITY_PRIVACY.md`
- Relevant sections of `docs/PRODUCT_REQUIREMENTS.md` and `docs/BUSINESS_LOGIC.md`
- Feature-specific docs such as `docs/CV_STUDIO_SPEC.md` when the AI task touches CVs.
- `docs/CV_INGESTION_EXTRACTION_SPEC.md` when AI touches CV extraction,
  OCR/layout/vision-LLM fallback, structuring, upload-and-name import, or template
  fill.
- `docs/API_CONTRACTS.md` if an API is exposed
- `docs/TEST_STRATEGY.md`

## Design Rules

- AI must solve real workflow pain, not decorate the UI.
- For uploaded CVs, AI is a fallback/enhancer after cheaper extraction tiers, not
  the first parser. Never send raw binary files to a model. A cheap vision-LLM tier
  MAY receive DOWNSCALED document images for the image / styled-or-scanned-PDF path
  (owner decision 2026-07-05, supersedes the older "text-only to LLM" rule for that
  path); the separate text-LLM structuring tier still receives extracted/redacted
  text or markdown only. Both are gated on AI settings/env.
- AI decisions are advisory unless docs explicitly say otherwise.
- Mutating tools require explicit confirmation and audit.
- Guests, students, partners, and ordinary university staff never see provider
  names, concrete model ids/model names, token counts, latency, prompts, raw
  confidence, chunk IDs, storage keys, routing internals, or internal status
  codes. Only platform superadmins may view or manage the real provider/model
  registry, and only inside superadmin AI operations/settings surfaces. API keys
  and base URLs are never returned at any privilege level.
- RAG answers cite document name/section and never answer from memory when documents are insufficient.

## Required Spec

For each AI task/tool define:

- Persona and workflow.
- Data sources and permission filters.
- Tool permission class: `read_only`, `confirmation_required`, `restricted_admin`, or `human_review`.
- Input/output schema.
- Side effects and audit event type.
- Prompt location/version owner.
- Fallback behavior.
- Rollback trigger.
- Evaluation set requirements.
- Usage/accounting policy and whether the feature is charged to student
  credits, partner org/package credits, or an internal university/platform
  budget. If a model call can affect quota/billing/budget, it must use a
  usage-aware path with durable ledger/idempotency.

## Output

Return an AI task matrix update, tool contract, safety risks, fallback/rollback criteria, and tests.
