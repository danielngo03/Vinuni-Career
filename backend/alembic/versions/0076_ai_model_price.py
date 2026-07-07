"""ai_model_price: admin-editable per-(provider, model) token price table.

Seeds initial price rows for the built-in gateway models derived from
``_BUILTIN_ROUTES`` in ``runtime_config.py`` and the blended per-1M rates
in ``cost_estimator.py``. All stored prices are in USD per 1 000 tokens
(per-1k = per-1M / 1000).

Sources:
- deepseek/deepseek-v4-flash: OpenRouter public pricing ~$0.07/$0.28 per 1M in/out
- deepseek/deepseek-r1:       OpenRouter public pricing ~$0.55/$2.19 per 1M in/out
- text-embedding-3-small:     OpenAI/OpenRouter public pricing ~$0.02 per 1M (no out)
- google/gemini-2.5-flash:    OpenRouter public pricing ~$0.15/$0.60 per 1M in/out
- deepseek/deepseek-chat:     ~$0.14/1M blended, split 50/50
- meta-llama/llama-3.1-8b-instruct: ~$0.10/1M blended, split 50/50
- gpt-4o-mini:                OpenAI public pricing ~$0.15/$0.60 per 1M in/out
- gpt-4o:                     OpenAI public pricing ~$2.50/$10.00 per 1M in/out

Revision ID: 0076_ai_model_price
Revises: 0075_skill_translation_cache
Create Date: 2026-07-07
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0076_ai_model_price"
down_revision: str | None = "0075_skill_translation_cache"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Seed rows: (provider, model, input_usd_per_1k, output_usd_per_1k)
# per-1M rates from cost_estimator.py / public OpenRouter/OpenAI pricing pages,
# converted to per-1k (divide by 1000).
_SEED_PRICES: list[tuple[str, str, float, float]] = [
    # -- OpenRouter / DeepSeek --
    # deepseek-v4-flash: fast chat default (~$0.07 in / $0.28 out per 1M)
    ("openrouter", "deepseek/deepseek-v4-flash", 0.00007, 0.00028),
    # deepseek-r1: reasoning default (~$0.55 in / $2.19 out per 1M)
    ("openrouter", "deepseek/deepseek-r1", 0.00055, 0.00219),
    # deepseek-chat: legacy alias model (~$0.14/1M blended, split 50/50)
    ("openrouter", "deepseek/deepseek-chat", 0.00007, 0.00028),
    # -- OpenRouter / Meta --
    # llama-3.1-8b-instruct: chat_mini (~$0.10/1M blended, split 50/50)
    ("openrouter", "meta-llama/llama-3.1-8b-instruct", 0.00005, 0.00005),
    # -- OpenRouter / Google --
    # gemini-2.5-flash: vision default (~$0.15 in / $0.60 out per 1M)
    ("openrouter", "google/gemini-2.5-flash", 0.00015, 0.00060),
    # -- OpenRouter / OpenAI embeddings --
    # text-embedding-3-small: embedding default (~$0.02/1M; no completion tokens)
    ("openrouter", "text-embedding-3-small", 0.00002, 0.0),
    # -- OpenAI direct --
    # gpt-4o-mini: chat_openai_fast (~$0.15 in / $0.60 out per 1M)
    ("openai", "gpt-4o-mini", 0.00015, 0.00060),
    # gpt-4o: chat_openai_best (~$2.50 in / $10.00 out per 1M)
    ("openai", "gpt-4o", 0.00250, 0.01000),
    # text-embedding-3-small via OpenAI direct (~$0.02/1M; no completion tokens)
    ("openai", "text-embedding-3-small", 0.00002, 0.0),
]


def upgrade() -> None:
    op.create_table(
        "ai_model_price",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("input_usd_per_1k", sa.Numeric(12, 8), nullable=False),
        sa.Column("output_usd_per_1k", sa.Numeric(12, 8), nullable=False),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("updated_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "provider", "model", name="uq_ai_model_price_provider_model"
        ),
    )

    # Seed known built-in model prices.
    price_table = sa.table(
        "ai_model_price",
        sa.column("id", sa.Uuid),
        sa.column("provider", sa.String),
        sa.column("model", sa.String),
        sa.column("input_usd_per_1k", sa.Numeric),
        sa.column("output_usd_per_1k", sa.Numeric),
        sa.column("active", sa.Boolean),
    )
    op.bulk_insert(
        price_table,
        [
            {
                "id": uuid.uuid4(),
                "provider": provider,
                "model": model,
                "input_usd_per_1k": input_per_1k,
                "output_usd_per_1k": output_per_1k,
                "active": True,
            }
            for provider, model, input_per_1k, output_per_1k in _SEED_PRICES
        ],
    )


def downgrade() -> None:
    op.drop_table("ai_model_price")
