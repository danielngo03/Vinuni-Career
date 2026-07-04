"""Application settings loaded from ``backend/.env`` via pydantic-settings.

All runtime configuration flows through :func:`get_settings`. Secrets (JWT key,
provider API keys) live only in ``backend/.env`` and are never logged or returned
to clients.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed view over environment configuration.

    Unknown env keys are ignored so the same ``.env`` can serve future modules
    without breaking Phase 0.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App runtime
    app_env: str = "local"
    app_name: str = "vinuni-career-platform"
    app_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"
    log_level: str = "INFO"
    debug: bool = False
    timezone: str = "Asia/Ho_Chi_Minh"
    default_locale: str = "vi"
    supported_locales: str = "vi,en"
    default_country: str = "VN"

    @field_validator("debug", mode="before")
    @classmethod
    def _coerce_debug(cls, value: Any) -> bool:
        """``DEBUG`` is boolean only (`true`/`false`/`1`/`0`).

        A parent shell that exports a non-boolean like ``DEBUG=release`` or
        ``DEBUG=prod`` (environment *names* belong in ``APP_ENV``) must never
        crash settings/tests — coerce any unrecognized value to the safe
        default ``False`` instead of raising. See ``docs/ENVIRONMENT.md``.
        """
        if isinstance(value, bool):
            return value
        if isinstance(value, (int,)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "on"}
        return False

    # Data services
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/vinuni_career"
    test_database_url: str = "sqlite+aiosqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/0"
    pgvector_enabled: bool = False

    # AI provider policy
    openrouter_api_key: str = "replace-with-local-key"
    openai_api_key: str = ""
    azure_openai_api_key: str = ""
    institution_email_domains: str = "vinuni.edu.vn"
    ai_default_provider: str = "openrouter"
    ai_default_model_alias: str = "chat_cheap"
    ai_reasoning_model_alias: str = "reasoning_cheap"
    ai_embedding_model_alias: str = "embedding_cheap"
    ai_rerank_model_alias: str = "rerank_cheap"
    ai_eval_model_alias: str = "eval_cheap"
    ai_real_calls_enabled: bool = False
    ai_max_real_calls_per_test_run: int = 3
    ai_daily_cost_limit_usd: float = 1.0
    # Per-user AI request allowances (counted from ai_usage_log rows; platform
    # policy, V1 flat). Two windows: the day resets at UTC midnight, the week
    # at UTC Monday. The gateway-facing guard blocks when EITHER is exhausted —
    # an exhausted week blocks requests even if today still has room.
    ai_daily_request_limit: int = 50
    ai_weekly_request_limit: int = 200
    openai_compatible_base_url: str = "https://openrouter.ai/api/v1"

    # OCR / extraction (lightweight defaults)
    backend_ai_extras: str = "ai-lite"
    local_ocr_engine: str = "auto"
    pdf_text_engine: str = "pdfplumber"
    docx_text_engine: str = "python-docx"
    ocr_fallback_engine: str = "tesseract"
    tesseract_ocr_langs: str = "vie+eng"
    paddle_ocr_enabled: bool = False
    cv_extraction_max_pages: int = 6
    cv_extraction_max_seconds: int = 25

    # CV ingestion engine policy (docs/CV_INGESTION_EXTRACTION_SPEC.md §4). Each
    # configured engine is resolved to an EFFECTIVE engine at runtime: the
    # configured value is used only when its dependency is importable, otherwise
    # the documented lightweight fallback is used (pdfplumber for native PDF,
    # ``none`` for layout, ``none`` for OCR -> records LOW_QUALITY_SCAN). These
    # are INTERNAL knobs; engine names never appear in any user-facing response.
    cv_native_pdf_engine: str = "pdfplumber"  # pymupdf4llm|pdfplumber
    cv_layout_engine: str = "none"  # none|pymupdf4llm|docling|marker
    cv_ocr_engine: str = "tesseract"  # none|tesseract|docling|marker
    cv_ocr_langs: str = "vie+eng"
    # LLM structuring is a TEXT-ONLY fallback, DISABLED by default. When enabled it
    # operates on extracted text/markdown only — never raw PDF/image bytes.
    cv_llm_structuring_enabled: bool = False
    cv_llm_structuring_provider_alias: str = "chat_cheap"
    # Ingestion runs through the background queue when true (resumable/idempotent);
    # the inline local queue executes it synchronously, so tests stay deterministic.
    cv_ingestion_async: bool = True

    # CV Studio quota (docs/CV_STUDIO_SPEC.md §5, docs/BUSINESS_LOGIC.md §4B.4).
    # Default student active CV library limit. "Active" = not soft-deleted and not
    # archived; archived/snapshot CVs do not count. Enforced server-side in the
    # documents service layer, not UI-only.
    # FUTURE HOOK: per-tier/per-university override. When a tier/quota config
    # mechanism lands, resolve the effective limit from it and fall back to this
    # default; callers read the limit through cv_service, never hardcode 5.
    student_active_cv_quota: int = 5

    # University moderation SLA (`docs/BUSINESS_LOGIC.md` moderation queue
    # workflow). Hours from submission (``submitted_at``) to the computed
    # ``due_by`` deadline surfaced in the moderation queue list/detail response.
    # Named constant so the moderation service layer never hardcodes "48".
    job_moderation_sla_hours: int = 48
    event_moderation_sla_hours: int = 48
    advertising_moderation_sla_hours: int = 48

    # Advertising / sponsored placements (ADR-0009). Max concurrent in-flight
    # (pending_approval | approved | active) placements per advertiser org; a
    # ``submit`` that would exceed this is rejected ``409 active_placement_limit``.
    advertising_max_active_per_org: int = 3

    # CV-to-job fit: a CV whose latest content update is older than this many days
    # is flagged ``stale: true`` in job-fit results (docs/BUSINESS_LOGIC.md §4B.3B,
    # docs/CV_STUDIO_SPEC.md §recommend). Deterministic; never a model parameter.
    cv_stale_after_days: int = 60

    # Storage
    storage_backend: str = "local"
    local_storage_dir: str = ".dev/storage"
    signed_url_ttl_seconds: int = 900
    max_upload_mb: int = 50
    # Organization logo upload cap (docs/API_CONTRACTS.md "Organization Media And
    # Logo Delivery", docs/SECURITY_PRIVACY.md). Default 3 MB. Logos are PUBLIC
    # marketing assets served by a stable public route, not a signed CV token.
    org_logo_max_mb: int = 3
    # Campaign creative (banner) upload cap. Public marketing media, served by a
    # stable public route (spec §5). Default 5 MB, magic-byte image allowlist.
    campaign_creative_max_mb: int = 5
    # VinUni-curated fallback banners (spec §5/§6). When NO active partner creative
    # exists for a primary public slot, the marketplace shows a university-curated
    # fallback asset (labelled curated, NEVER paid). These point at a static
    # ``frontend/public`` asset path (e.g. ``/images/career-day-2026.jpg``). Empty
    # (default) means no fallback is rendered for that slot — curated content is
    # never fabricated; it must be explicitly configured or seeded.
    marketplace_hero_fallback_image: str = ""
    marketplace_rail_fallback_image: str = ""
    # Optional Unicode TTF for CV PDF export (Vietnamese). Empty -> auto-detect
    # a system font, else latin-1-safe fallback (local dev only).
    cv_pdf_font_path: str = ""

    # Auth / session / device
    jwt_secret_key: str = "local-dev-only-insecure-change-me"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    session_device_limit: int = 10
    admin_totp_required: bool = False
    account_lockout_failures: int = 5
    account_lockout_minutes: int = 15
    password_reset_ttl_minutes: int = 60
    geoip_enabled: bool = False
    geoip_city_level_only: bool = True

    # Refresh-token cookie (httpOnly). The ``secure`` flag is derived from the env
    # unless explicitly overridden so local http dev works without disabling
    # security in non-local environments (``docs/SECURITY_PRIVACY.md`` §8).
    auth_refresh_cookie_name: str = "vinuni_refresh"
    auth_cookie_secure: bool | None = None  # None -> derive from app_env

    # Discovery / guest personalization (privacy-safe first-party session).
    # The discovery cookie holds ONLY a random session id (no PII); coarse signals
    # live server-side in ``discovery_sessions.coarse_tags`` (allowlisted). TTL is
    # short; events are retained longer for analytics, then pruned by the cleanup
    # sweep (``docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md`` §3/§8).
    discovery_session_cookie_name: str = "vinuni_discovery"
    discovery_session_ttl_days: int = 30
    discovery_event_retention_days: int = 90

    # Short-lived signed token bridging password verification and the TOTP step.
    totp_challenge_ttl_minutes: int = 5
    # Fernet key (urlsafe base64) for TOTP secret encryption at rest. Empty ->
    # derive deterministically from ``jwt_secret_key`` (local dev only). Production
    # MUST set ``TOTP_ENCRYPTION_KEY`` in ``backend/.env`` (``docs/ENVIRONMENT.md``).
    totp_encryption_key: str = ""
    # Fernet key for admin-managed AI provider API keys. Empty uses a local-dev
    # derivation from ``jwt_secret_key``; production should set a real key.
    ai_provider_key_encryption_key: str = ""

    # Email / notifications
    email_provider: str = "local"  # "local" | "smtp"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_use_ssl: bool = False  # True for port 465 (SSL), False for 587 (STARTTLS)
    smtp_timeout: int = 30
    smtp_username: str = ""
    smtp_password: str = ""
    email_from_address: str = "career@vinuni.edu.vn"
    email_from_name: str = "VinUni Career Center"
    # OTP settings
    otp_ttl_minutes: int = 10
    otp_max_attempts: int = 3
    otp_rate_limit_per_hour: int = 3
    # Anti-enumeration cooldown/rate limit for resend-verification, forgot-password,
    # and register-resume, keyed by the normalized email itself (never user id) so
    # behaviour is identical whether or not the email maps to a real account
    # (docs/EDGE_CASES_FAILURE_MODES.md, docs/SECURITY_PRIVACY.md).
    auth_resend_cooldown_seconds: int = 60
    auth_email_request_rate_limit_per_hour: int = 5

    # OAuth / OIDC social login (Google / Facebook). Empty client id/secret ->
    # `/auth/oauth/{provider}/start` returns a clean 400 `oauth_not_configured`
    # instead of crashing or redirecting to a broken provider URL (local dev
    # default has no real OAuth app registered).
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    facebook_oauth_client_id: str = ""
    facebook_oauth_client_secret: str = ""
    # Base URL the OAuth callback is registered against with the provider. Empty ->
    # derive from `app_url` (mirrors the `frontend_url` derivation pattern).
    oauth_redirect_base_url: str = ""
    # TTL for the short-lived signed OAuth state token (CSRF) and the post-callback
    # one-time ticket exchanged by the frontend for real session tokens.
    oauth_state_ttl_minutes: int = 10
    oauth_ticket_ttl_minutes: int = 2
    notification_email_enabled: bool = True
    notification_push_enabled: bool = False
    notification_digest_enabled: bool = True
    email_template_editor_enabled: bool = True

    # Jobs / observability
    # ``inline`` (default) runs enqueued work in-process; ``scheduler`` is the
    # standalone ``python -m app.worker`` periodic loop (ADR-0003). The API process
    # never starts the loop — only ``app.worker`` does, and only when this is
    # ``scheduler``. Tests keep ``inline`` so no loop is ever spawned.
    background_worker_mode: str = "inline"
    # Outbox dead-letter threshold: after this many delivery attempts a transient
    # send failure becomes terminal ``dead`` instead of retrying (ADR-0003 §3).
    outbox_max_attempts: int = 5
    # Base interval of the scheduler tick loop; each registered job fires at its own
    # multiple of this (outbox 15s, reveal 5m, deadline 10m) (ADR-0003 §1).
    scheduler_base_tick_seconds: int = 15
    # B-558 read-model governance: the market-intelligence snapshot is considered
    # fresh for this long after ``computed_at`` before a read falls back to a
    # live recompute (the scheduled refresh runs well inside this window).
    market_intelligence_stale_after_seconds: int = 1800
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Messaging anti-spam ceilings (ADR-0012 §1). Counted at the service layer from
    # ``messages``/``message_threads`` since the start of the current UTC day; no new
    # table. ``inactive_application_daily_cap`` is the BUSINESS_LOGIC §14.1 "max 3/day"
    # taper applied to a partner posting into a thread whose bound application has
    # gone terminal/inactive.
    messaging_max_messages_per_sender_per_day: int = 200
    messaging_max_threads_per_sender_per_day: int = 30
    messaging_inactive_application_daily_cap: int = 3
    # Own-message soft-delete window (ADR-0012 §5 / BUSINESS_LOGIC §14.3).
    messaging_delete_window_minutes: int = 10

    audit_log_enabled: bool = True
    pii_log_redaction_enabled: bool = True
    ai_trace_ttl_days: int = 30

    # CORS
    cors_allow_origins: str = "http://localhost:3000"

    @property
    def supported_locales_list(self) -> list[str]:
        return [item.strip() for item in self.supported_locales.split(",") if item.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        return [item.strip() for item in self.cors_allow_origins.split(",") if item.strip()]

    @property
    def refresh_cookie_secure(self) -> bool:
        """Whether the refresh cookie sets ``Secure`` (HTTPS-only).

        Explicit ``AUTH_COOKIE_SECURE`` wins; otherwise ``Secure`` is on for every
        environment except ``local`` (so http://localhost dev still receives the
        cookie). Never hardcoded insecure for shipped environments.
        """

        if self.auth_cookie_secure is not None:
            return self.auth_cookie_secure
        return self.app_env.lower() != "local"

    @property
    def refresh_cookie_max_age(self) -> int:
        return self.refresh_token_ttl_days * 24 * 3600

    @property
    def discovery_cookie_max_age(self) -> int:
        return self.discovery_session_ttl_days * 24 * 3600

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def org_logo_max_bytes(self) -> int:
        return self.org_logo_max_mb * 1024 * 1024

    @property
    def campaign_creative_max_bytes(self) -> int:
        return self.campaign_creative_max_mb * 1024 * 1024

    @property
    def effective_oauth_redirect_base_url(self) -> str:
        """The base URL OAuth callbacks are registered against.

        Explicit ``OAUTH_REDIRECT_BASE_URL`` wins; otherwise derived from
        ``app_url`` (the backend API origin, since providers redirect to our
        ``/api/v1/auth/oauth/{provider}/callback`` route, not the frontend).
        """

        return (self.oauth_redirect_base_url or self.app_url).rstrip("/")


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()
