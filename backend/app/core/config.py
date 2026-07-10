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
    # Concrete per-slot models (admin/.env authoritative; seed the *_default
    # slot bindings). Model ids are internal — never exposed to end users.
    ai_chat_model: str = "deepseek/deepseek-v4-flash"
    ai_reasoning_model: str = "deepseek/deepseek-r1"
    ai_embedding_model: str = "text-embedding-3-small"
    ai_rerank_model: str = "deepseek/deepseek-v4-flash"
    ai_eval_model: str = "deepseek/deepseek-v4-flash"
    ai_vision_model: str = "google/gemini-2.5-flash"
    # Function-slot handles bound to the concrete models above. These leak-safe
    # role names (never a vendor/model string) are the only identifiers passed
    # through the gateway and stored on the ai_settings row.
    ai_default_model_alias: str = "chat_default"
    ai_reasoning_model_alias: str = "reasoning_default"
    ai_embedding_model_alias: str = "embedding_default"
    ai_rerank_model_alias: str = "rerank_default"
    ai_eval_model_alias: str = "eval_default"
    ai_real_calls_enabled: bool = False
    ai_max_real_calls_per_test_run: int = 3
    # Platform-wide daily AI cost ceiling (superadmin safety net). This is the
    # PLATFORM budget consumed by ``ai_settings`` / ``budget_guard`` — NOT a
    # per-student daily limit. Retained after the daily student windows were
    # removed (WS-1).
    ai_daily_cost_limit_usd: float = 1.0
    # Per-user AI request allowance (counted from ai_usage_log rows; platform
    # policy, V1 flat). Single weekly window, resets at UTC Monday. The daily
    # request-count window was removed (WS-1) — cost-weighted metering is now the
    # masked-energy account; this weekly cap is a coarse safety net for chat.
    ai_session_request_limit: int = 50
    ai_session_window_hours: int = 3
    ai_weekly_request_limit: int = 200
    openai_compatible_base_url: str = "https://openrouter.ai/api/v1"

    # --- Mock Interview: conversational "brain" model ---------------------------
    # The turn-by-turn interviewer engine AND the post-session coaching report run
    # through the SAME safe text gateway as every other AI task (guard + fallback +
    # usage log + telemetry + eval sampling). Bound to a leak-safe alias; the
    # concrete model id is internal. Gemini 2.5 Flash reads/writes Vietnamese well
    # and is fast + cheap, which matters for a low-latency spoken interview. Any
    # OpenAI-compatible model works — a superadmin can rebind the alias in the
    # provider registry without touching code.
    ai_interview_model: str = "google/gemini-2.5-flash"
    ai_interview_model_alias: str = "interview_default"

    # --- Mock Interview: realtime speech-to-speech tier (Tier V2) ---------------
    # TRUE full-duplex voice needs a NATIVE provider socket (Gemini Live via
    # WebSocket / OpenAI Realtime via WebRTC) and that provider's own key — it
    # CANNOT be proxied through an OpenAI-compatible TEXT endpoint like OpenRouter.
    # It is therefore DISABLED by default: the default spoken experience is
    # browser-native STT/TTS driving the text brain above (Tier V1), which runs on
    # the existing OpenRouter key at ~zero extra provider cost. A platform
    # superadmin enables Tier V2 by registering a realtime provider+model+voice
    # (plus its own key) in the AI registry and flipping ``ai_realtime_enabled``.
    # All values are leak-safe aliases; no vendor/model string reaches end users.
    ai_realtime_enabled: bool = False  # OFF until a NATIVE realtime key is present
    ai_realtime_provider: str = "gemini-live"  # registry alias (superadmin-swappable)
    # Native speech-to-speech model (Gemini Live). Default = the natural-voice
    # "Native Audio Dialog"; alternatives your project may expose:
    # gemini-3-flash-live-preview, gemini-2.5-flash-native-audio-preview-09-2025.
    ai_realtime_model: str = "gemini-2.5-flash-preview-native-audio-dialog"
    ai_realtime_voice: str = "Aoede"  # provider voice name (Aoede/Puck/Charon/…)
    ai_realtime_ttl_seconds: int = 660  # ephemeral-token / session hard-cap ceiling
    # Native Gemini/Google AI key for the realtime Live tier (NOT OpenRouter).
    # Also read from GEMINI_API_KEY / GOOGLE_API_KEY / AI_PROVIDER_GEMINI_LIVE_API_KEY.
    gemini_api_key: str = ""

    # --- Mock Interview: server-mediated Gemini voice tier (STT + TTS) ----------
    # A turn-based spoken interview that runs on a Google/Vertex GenAI key WITHOUT
    # the AI-Studio ephemeral-token Live socket: the server transcribes the
    # student's spoken answer (Gemini audio understanding) and synthesizes the
    # interviewer's question to natural speech (Gemini TTS), reusing the existing
    # CV+JD-grounded text turn engine in between. This works on a Vertex *express*
    # API key (``genai.Client(vertexai=True, api_key=...)``), unlike the native
    # Live tier which requires an AI-Studio key. Values are leak-safe; no vendor or
    # model string reaches the student. Disabled by default; enable once a working
    # Google key + ``AI_REAL_CALLS_ENABLED`` are present.
    ai_speech_enabled: bool = False
    ai_speech_use_vertex: bool = True  # express Vertex key path (vertexai=True)
    ai_speech_tts_model: str = "gemini-2.5-flash-preview-tts"
    ai_speech_stt_model: str = "gemini-2.5-flash"
    ai_speech_voice: str = "Aoede"  # Gemini prebuilt voice (Aoede/Puck/Charon/Kore/…)
    ai_speech_max_tts_chars: int = 1200  # cap synthesized text length per call
    ai_speech_max_audio_seconds: int = 90  # cap uploaded answer audio length
    ai_speech_max_audio_bytes: int = 8 * 1024 * 1024  # hard upload ceiling (8 MB)

    # Google Cloud / Vertex AI binding for the speech tier (and any future native
    # Google model). ``google_application_credentials`` is a FILE PATH to a
    # service-account JSON key — the file itself lives OUTSIDE the repo and is
    # never committed; only its path is configured here. When set, the speech
    # client authenticates via ADC (full quota) instead of an express API key.
    google_cloud_project: str = ""
    google_cloud_location: str = "global"
    google_application_credentials: str = ""

    # --- Mock Interview: TRUE realtime Live relay (server-mediated) --------------
    # Full-duplex native-audio interview via the Gemini Live model. The browser
    # cannot hold the Google service-account credential, so the SERVER brokers the
    # Live socket (ADC), relaying the student's mic audio in and the interviewer's
    # native-audio out with live transcripts. This is the low-latency "live" tier;
    # the turn-based STT+TTS tier above is the fallback. Region-pinned because the
    # Live model is only served from specific Vertex regions (not ``global``).
    ai_realtime_relay_enabled: bool = False
    ai_realtime_relay_model: str = "gemini-live-2.5-flash-native-audio"
    ai_realtime_relay_location: str = "us-central1"

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
    cv_llm_structuring_provider_alias: str = "chat_default"
    # Ingestion runs through the background queue when true (resumable/idempotent);
    # the inline local queue executes it synchronously, so tests stay deterministic.
    cv_ingestion_async: bool = True

    # Vision-LLM extraction tier (docs/CV_INGESTION_EXTRACTION_SPEC.md §3.5).
    # PRODUCT DECISION (owner-approved 2026-07-05): image and scanned-CV uploads
    # may be sent to a cheap multimodal model that performs OCR + structuring in a
    # single call, because local Tesseract OCR is unreliable on the styled,
    # multi-column CV templates students actually upload. This tier is
    # cost-optimized: it runs ONLY when native text and local OCR fail to yield a
    # reliable parse (never on text PDFs), uses the cheapest capable vision model,
    # downscales images before upload, and caps the number of pages sent.
    # The concrete model id is resolved via the alias (never exposed to users).
    cv_vision_extraction_enabled: bool = True
    cv_vision_provider_alias: str = "vision_default"
    cv_vision_max_image_px: int = 2200  # long-edge cap; controls token cost
    cv_vision_max_pages: int = 4  # max rasterized pages sent per scanned PDF

    # JD (job description) upload extraction engine. Mirrors the CV cascade knobs
    # but independent so partner JD tuning never affects student CV parsing.
    # Cost-tiered: native text (free) -> local OCR -> cheap vision-LLM for images
    # and styled/scanned PDFs -> text-LLM structuring. Extraction is auto-fill
    # ONLY (never persisted). Engine names never appear in user-facing responses.
    jd_max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB
    jd_ocr_langs: str = "vie+eng"
    jd_vision_extraction_enabled: bool = True
    jd_vision_provider_alias: str = "vision_default"
    jd_vision_max_image_px: int = 2200  # long-edge cap; controls vision token cost
    jd_vision_max_pages: int = 3  # JDs are short; cap rasterized pages tightly
    jd_llm_structuring_provider_alias: str = "chat_default"
    jd_extraction_max_seconds: int = 25

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

    # Campaign-grade allocation engine (spec §7.0). Max concurrent in-flight
    # (pending_review | approved | active | paused) CAMPAIGNS per advertiser org.
    advertising_max_active_campaigns_per_org: int = 5
    # Default frozen CPM (cost per 1000 impressions, VND) used to derive a
    # campaign's notional impression goal + per-impression spend for budget pacing.
    # V1 has no bidding; this is a fixed rate-card value, frozen onto the campaign
    # at submit. Never surfaced as a "bid" — it is an internal spend/pacing rate.
    advertising_default_cpm_vnd: str = "50000.00"
    # TTL (seconds) an allocation-plan row stays "current" before recomputation.
    advertising_allocation_ttl_seconds: int = 600

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
    # Fernet key(s) for admin-managed AI provider API keys.
    # ``ai_provider_key_encryption_keys`` is a comma-separated list, NEWEST KEY
    # FIRST, enabling zero-downtime rotation via MultiFernet (encrypt with the
    # first key, decrypt with any). Production (app_env != local) MUST configure
    # a key or startup fails; local dev derives one from ``jwt_secret_key`` with
    # a warning. The singular ``ai_provider_key_encryption_key`` is kept for
    # backward compatibility and used when the plural form is empty.
    ai_provider_key_encryption_keys: str = ""
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

    # Langfuse observability (optional; all three must be set to enable tracing).
    # Keys are secret credentials — never log or return them. When absent the
    # langfuse_client module runs in no-op mode.
    langfuse_secret_key: str | None = None
    langfuse_public_key: str | None = None
    langfuse_base_url: str | None = None

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
