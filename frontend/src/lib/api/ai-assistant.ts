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

/** One AI quota window (day or week) for the sidebar meter. */
export interface AiUsageWindow {
  used: number;
  limit: number;
  pct: number;
}

/** AI request usage for the sidebar meter (`GET /ai/usage/me`).
 * Request counts only — the backend never exposes cost/token/provider data.
 * `blocked` mirrors the gateway gate: when either window is exhausted, new AI
 * requests are refused with 409 QUOTA_EXCEEDED (week dominates day). */
export interface AiUsageSummary {
  day: AiUsageWindow;
  week: AiUsageWindow;
  warning: boolean;
  blocked: boolean;
  blocked_scope: "day" | "week" | null;
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

/** Rich AI usage detail for the billing/usage panel (`GET /ai/usage/summary`).
 * Extends the sidebar meter with reset timing, a per-feature breakdown, and a
 * recent-activity list. Still request-count only: no provider/model/token/cost. */
export interface AiUsageDetail extends AiUsageSummary {
  /** ISO-8601 UTC instant the daily window resets. */
  day_reset: string;
  /** ISO-8601 UTC instant the weekly window resets. */
  week_reset: string;
  /** Number of days the breakdown/total cover (default 30). */
  window_days: number;
  /** Total AI requests in the window (includes system tasks not shown by feature). */
  total: number;
  by_feature: AiUsageFeatureCount[];
  recent: AiUsageActivity[];
}

export const aiAssistantApi = {
  /** My AI usage today vs the daily allowance. */
  myUsage(): Promise<AiUsageSummary> {
    return api.get<AiUsageSummary>("/ai/usage/me");
  },

  /** My AI usage detail for the billing/usage panel (windows, reset timing,
   * per-feature breakdown, recent activity). */
  myUsageDetail(): Promise<AiUsageDetail> {
    return api.get<AiUsageDetail>("/ai/usage/summary");
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
