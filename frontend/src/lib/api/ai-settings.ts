import { api } from "./client";

/* ------------------------------- Vocabularies ----------------------------- */

/**
 * The four AI task families an admin governs (ADR-0011 §1). Each family exposes
 * an ALIAS NAME selection only — never a concrete provider/model id. The
 * alias→concrete-model mapping stays in backend env/config; this surface only
 * ever sees alias names like `chat_cheap`.
 */
export type AiModelFamily = "chat" | "reasoning" | "embedding" | "rerank" | "eval";

export const AI_MODEL_FAMILIES: AiModelFamily[] = [
  "chat",
  "reasoning",
  "embedding",
  "rerank",
  "eval",
];

/**
 * Rollout control (ADR-0011 §5). `paused`/`offline` force real calls off while
 * preserving the selected aliases/flags for a clean re-enable.
 */
export type AiRolloutState = "enabled" | "paused" | "offline";

export const AI_ROLLOUT_STATES: AiRolloutState[] = [
  "enabled",
  "paused",
  "offline",
];

/**
 * Derived real-calls status (ADR-0011 §3 — secrecy). This is the ONLY signal an
 * admin gets about whether AI is live, and it never reveals the provider/model/key:
 * - `offline`   = env gate off OR no provider key configured (admin cannot override).
 * - `available` = env+key OK but the admin toggle/rollout keeps real calls off.
 * - `enabled`   = real calls are fully active.
 */
export type AiRealCallsStatus = "offline" | "available" | "enabled";

/* ------------------------------- Wire types ------------------------------- */

/** Per-family selected alias NAME (no provider/model id, ever). */
export type AiModelAliases = Record<AiModelFamily, string>;

/** Per-family selectable alias NAMES (the allowlist the selectors render from). */
export type AiAllowedAliases = Record<AiModelFamily, string[]>;

export interface AiFeatureFlags {
  /** CV upload → LLM structuring fallback. */
  cv_llm_structuring_enabled: boolean;
  /** Job-fit enrichment AI explanation. */
  job_fit_ai_explanation_enabled: boolean;
}

/**
 * Masked, admin-facing AI settings (`GET /admin/ai-settings`). Alias NAMES +
 * flags + budget + DERIVED status only. Provider keys are write-only through
 * the provider registry and are never returned here.
 */
export interface AiSettings {
  scope: string;
  /** Selected alias NAME per family. */
  models: AiModelAliases;
  /** Selectable alias NAMES per family (drives the selectors). */
  allowed_aliases: AiAllowedAliases;
  feature_flags: AiFeatureFlags;
  /** Per-day USD ceiling as a decimal string, e.g. "1.00". */
  daily_budget_usd: string;
  /** Per-org daily USD cap as a decimal string, or null when no cap is set. */
  per_org_daily_budget_usd: string | null;
  rollout_state: AiRolloutState;
  /** The admin DB toggle (gated under the env/key ceiling — may be inert). */
  real_calls_enabled: boolean;
  /** Whether a provider key is configured (presence only — never the key). */
  key_configured: boolean;
  /** Derived tri-state — see {@link AiRealCallsStatus}. */
  real_calls: AiRealCallsStatus;
  /** Optimistic-concurrency marker echoed by the backend. */
  version: number;
  updated_at: string | null;
}

/**
 * Partial update (`PATCH /admin/ai-settings`). Only provided fields change.
 * There is NO key/base_url/provider/model field in settings. Provider keys are
 * managed through the provider registry as write-only values.
 * Aliases must come from `allowed_aliases[family]`; budget is 0–10000.
 */
export interface AiSettingsUpdateBody {
  chat_model_alias?: string;
  reasoning_model_alias?: string;
  embedding_model_alias?: string;
  rerank_model_alias?: string;
  eval_model_alias?: string;
  cv_llm_structuring_enabled?: boolean;
  job_fit_ai_explanation_enabled?: boolean;
  real_calls_enabled?: boolean;
  rollout_state?: AiRolloutState;
  daily_budget_usd?: number;
  /** Set a per-org cap (USD). Pass alongside clear_per_org_budget to avoid ambiguity. */
  per_org_daily_budget_usd?: number;
  /** Set true to remove the per-org cap (sets field to null). */
  clear_per_org_budget?: boolean;
  notes?: string;
}

/** Maps a family to its PATCH alias field name. */
export const AI_ALIAS_FIELD: Record<AiModelFamily, keyof AiSettingsUpdateBody> = {
  chat: "chat_model_alias",
  reasoning: "reasoning_model_alias",
  embedding: "embedding_model_alias",
  rerank: "rerank_model_alias",
  eval: "eval_model_alias",
};

/* ----------------------- Multi-provider registry types -------------------- */

export type AiProviderType = "openai_compatible" | "ollama" | "azure_openai";

export const AI_PROVIDER_TYPES: { value: AiProviderType; label: string }[] = [
  { value: "openai_compatible", label: "OpenAI-compatible (REST)" },
  { value: "ollama", label: "Ollama (local)" },
  { value: "azure_openai", label: "Azure OpenAI" },
];

export interface AiProvider {
  id: string;
  name: string;
  provider_type: AiProviderType;
  base_url: string;
  description: string | null;
  is_active: boolean;
  is_builtin: boolean;
  has_api_key: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface AiProviderCreateBody {
  name: string;
  provider_type: AiProviderType;
  base_url: string;
  api_key?: string;
  description?: string;
}

export interface AiProviderUpdateBody {
  base_url?: string;
  api_key?: string;
  clear_api_key?: boolean;
  description?: string;
  is_active?: boolean;
  provider_type?: AiProviderType;
}

/** Admin-facing alias row — model_id intentionally absent from GET responses. */
export interface AiModelAliasRow {
  id: string;
  alias_name: string;
  provider_id: string;
  provider_name: string | null;
  task_families: string | null;
  description: string | null;
  is_active: boolean;
  is_builtin: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface AiAliasCreateBody {
  alias_name: string;
  /** Concrete model identifier sent to the provider (e.g. "deepseek/deepseek-chat"). */
  model_id: string;
  provider_id: string;
  task_families?: string;
  description?: string;
}

export interface AiAliasUpdateBody {
  model_id?: string;
  provider_id?: string;
  task_families?: string;
  description?: string;
  is_active?: boolean;
}

/* --------------------------------- Calls ---------------------------------- */

export const aiSettingsApi = {
  /**
   * Masked effective AI settings. University moderators / superadmin only
   * (`ai_settings:read`); partners/students get 403/404 (no entry point).
   */
  get(): Promise<AiSettings> {
    return api.get<AiSettings>("/admin/ai-settings");
  },

  /**
   * Update aliases / flags / budget / rollout (`ai_settings:manage`). Returns the
   * updated masked settings. 422 (`reason: "alias_not_allowed" | "out_of_range"`)
   * on an off-allowlist alias or out-of-range budget.
   */
  update(body: AiSettingsUpdateBody): Promise<AiSettings> {
    return api.patch<AiSettings>("/admin/ai-settings", body);
  },

  /**
   * Kill switch (ADR-0011 §5): forces real calls off + rollout `offline`,
   * immediately. Returns the updated masked settings.
   */
  disable(reason?: string): Promise<AiSettings> {
    return api.post<AiSettings>("/admin/ai-settings/disable-ai", { reason });
  },
};

export const aiProvidersApi = {
  list(): Promise<AiProvider[]> {
    return api.get<AiProvider[]>("/admin/ai-settings/providers");
  },
  create(body: AiProviderCreateBody): Promise<AiProvider> {
    return api.post<AiProvider>("/admin/ai-settings/providers", body);
  },
  update(id: string, body: AiProviderUpdateBody): Promise<AiProvider> {
    return api.patch<AiProvider>(`/admin/ai-settings/providers/${id}`, body);
  },
};

export const aiAliasesApi = {
  list(): Promise<AiModelAliasRow[]> {
    return api.get<AiModelAliasRow[]>("/admin/ai-settings/model-aliases");
  },
  create(body: AiAliasCreateBody): Promise<AiModelAliasRow> {
    return api.post<AiModelAliasRow>("/admin/ai-settings/model-aliases", body);
  },
  update(id: string, body: AiAliasUpdateBody): Promise<AiModelAliasRow> {
    return api.patch<AiModelAliasRow>(`/admin/ai-settings/model-aliases/${id}`, body);
  },
};
