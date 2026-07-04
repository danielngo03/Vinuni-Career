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
  OCR/layout fallback, structuring, review/import, or template fill.
- `docs/API_CONTRACTS.md` if an API is exposed
- `docs/TEST_STRATEGY.md`

## Design Rules

- AI must solve real workflow pain, not decorate the UI.
- For uploaded CVs, AI is a fallback/enhancer after local extraction, not the
  first parser. Never send raw binary files to a model; send extracted/redacted
  text or markdown only when enabled.
- AI decisions are advisory unless docs explicitly say otherwise.
- Mutating tools require explicit confirmation and audit.
- End users never see provider names, model names, token counts, latency, prompts, raw confidence, chunk IDs, storage keys, or internal status codes.
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

## Output

Return an AI task matrix update, tool contract, safety risks, fallback/rollback criteria, and tests.
