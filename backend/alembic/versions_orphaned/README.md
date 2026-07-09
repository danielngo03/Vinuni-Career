# Orphaned / out-of-lineage migrations

Files here are NOT part of the active Alembic chain and are intentionally
excluded from `versions/` so they are not loaded or applied.

- `0084_ai_provider_health_fields.py` — WIP from an uncommitted working tree
  that ALTERs an `ai_provider` table which does not exist in the `vinuni_career`
  database (that table belongs to the separate ai-provider-model-admin feature,
  not applied here). It cannot run against this DB and would create a second
  Alembic head. Preserved here so the work is not lost; re-home it onto the
  ai-provider-model-admin lineage if/when that feature lands.

The live DB follows the partner-ai-overhaul migration lineage
(`0084_ai_energy_accounts_and_usage_org` … `0089_chat_message_seq_softdelete_edited`),
now vendored into `versions/`, with partner-chatbot work chained after 0089
(`0090_chat_export_files`, …).
