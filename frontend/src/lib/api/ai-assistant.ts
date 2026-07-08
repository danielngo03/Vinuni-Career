import { api } from "./client";

/* ------------------------------- Wire types ------------------------------- */

export interface ChatSession {
  id: string;
  title: string | null;
  persona: string;
  created_at: string;
  last_message_at: string | null;
}

export type ChatMessageRole =
  | "user"
  | "assistant"
  | "tool_call"
  | "tool_result";

export interface ChatMessage {
  id: string;
  session_id: string;
  role: ChatMessageRole;
  content: string;
  tool_name: string | null;
  tool_args: Record<string, unknown> | null;
  tool_result: Record<string, unknown> | null;
  requires_confirmation: boolean;
  confirmed_at: string | null;
  created_at: string;
}

/* --------------------------------- Calls ---------------------------------- */

/** Whether the energy budget is a shared partner-org pool or a personal one. */
export type AiEnergyScope = "org" | "user";

/** Weekly AI energy budget, expressed in opaque "energy" credits.
 * These are NOT tokens, USD, or provider units — the backend deliberately masks
 * cost so no provider/model/token/price signal ever reaches the client.
 *   - `used`:      credits spent this week
 *   - `allowance`: base weekly grant from the plan/entitlement
 *   - `wallet`:    extra top-up/reserve credits on top of the allowance
 *   - `capacity`:  total spendable this week (allowance + wallet) */
export interface AiEnergyWeekly {
  used: number;
  allowance: number;
  wallet: number;
  capacity: number;
}

/** Rolling 3-hour burst window. `over_soft_cap` means recent activity crossed
 * the soft pacing threshold (a warning, not a hard block). */
export interface AiEnergySession3h {
  used: number;
  soft_cap: number;
  over_soft_cap: boolean;
}

/** Reason a caller is hard-blocked from new AI actions (weekly energy spent). */
export type AiEnergyBlockedReason =
  | "AI_WEEKLY_ENERGY_EXCEEDED"
  | "AI_ORG_WEEKLY_ENERGY_EXCEEDED";

/** Reason a caller is being warned (burst pacing, nearing the weekly limit, or
 * an already-exceeded weekly/org budget surfaced as a soft warning). */
export type AiEnergyWarningReason =
  | "AI_SESSION_BURST"
  | "AI_WEEKLY_NEARING_LIMIT"
  | "AI_WEEKLY_ENERGY_EXCEEDED"
  | "AI_ORG_WEEKLY_ENERGY_EXCEEDED";

/** AI energy usage for the sidebar meter (`GET /ai/usage/me`).
 * Cost-weighted "energy" model (owner-locked 2026-07-08). The headline is
 * `energy_pct` — the share of this week's energy that is still REMAINING (0..100).
 * The backend never exposes cost/token/provider/model data; `weekly` counts are
 * opaque energy credits. `blocked` mirrors the gateway gate: when the weekly (or
 * shared org) energy is exhausted, new AI actions are refused. */
export interface AiEnergyUsage {
  /** "org" = shared partner-org pool; "user" = the caller's personal budget. */
  scope: AiEnergyScope;
  /** Remaining weekly energy, 0..100 (headline). */
  energy_pct: number;
  weekly: AiEnergyWeekly;
  session_3h: AiEnergySession3h;
  blocked: boolean;
  blocked_reason: AiEnergyBlockedReason | null;
  warning: boolean;
  warning_reason: AiEnergyWarningReason | null;
  /** ISO-8601 UTC instant the weekly energy budget resets. */
  week_reset: string;
}

/** One product-feature bucket in the usage breakdown. `feature` is a stable
 * code the client localizes (`billing.usage.features.*`) — never a raw internal
 * task/model label. */
export interface AiUsageFeatureCount {
  feature: string;
  count: number;
}

/** One recent AI activity row. Request metadata only — no cost/token/provider. */
export interface AiUsageActivity {
  feature: string;
  ok: boolean;
  at: string | null;
}

/** Rich AI energy detail for the billing/usage panel (`GET /ai/usage/summary`).
 * Extends the sidebar meter with the reporting window, a per-feature breakdown,
 * and a recent-activity list. Still masked: no provider/model/token/cost. */
export interface AiEnergyUsageDetail extends AiEnergyUsage {
  /** Number of days the breakdown/total cover (default 30). */
  window_days: number;
  /** Total AI actions in the window (includes system tasks not shown by feature). */
  total: number;
  by_feature: AiUsageFeatureCount[];
  recent: AiUsageActivity[];
}

export const aiAssistantApi = {
  /** My remaining AI energy for this week (sidebar meter). */
  myUsage(): Promise<AiEnergyUsage> {
    return api.get<AiEnergyUsage>("/ai/usage/me");
  },

  /** My AI energy detail for the billing/usage panel (weekly budget, burst
   * window, reset timing, per-feature breakdown, recent activity). */
  myUsageDetail(): Promise<AiEnergyUsageDetail> {
    return api.get<AiEnergyUsageDetail>("/ai/usage/summary");
  },

  /** Create a new chat session. */
  createSession(): Promise<ChatSession> {
    return api.post<ChatSession>("/ai/chat/sessions", {});
  },

  /** List the caller's recent sessions. */
  listSessions(): Promise<ChatSession[]> {
    return api.get<ChatSession[]>("/ai/chat/sessions");
  },

  /** Get messages for a session. */
  getMessages(sessionId: string): Promise<ChatMessage[]> {
    return api.get<ChatMessage[]>(`/ai/chat/sessions/${sessionId}/messages`);
  },

  /** Send a message; receive the assistant's reply. */
  sendMessage(sessionId: string, text: string): Promise<ChatMessage> {
    return api.post<ChatMessage>(`/ai/chat/sessions/${sessionId}/messages`, {
      text,
    });
  },

  /** Confirm and execute a pending tool action. */
  confirmToolAction(
    sessionId: string,
    messageId: string,
  ): Promise<{ confirmed: ChatMessage; reply: ChatMessage }> {
    return api.post<{ confirmed: ChatMessage; reply: ChatMessage }>(
      `/ai/chat/sessions/${sessionId}/messages/${messageId}/confirm`,
      {},
    );
  },

  /** Archive (soft-delete) a session. */
  archiveSession(sessionId: string): Promise<{ status: string }> {
    return api.delete<{ status: string }>(`/ai/chat/sessions/${sessionId}`);
  },
};
