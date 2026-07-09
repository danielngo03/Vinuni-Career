import { api, apiUpload } from "./client";

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

/** One AI quota window for the sidebar meter. */
export interface AiUsageWindow {
  used: number;
  limit: number;
  /** Percent USED, 0-100 (drives the meter fill + warn/block thresholds). */
  pct: number;
  /** ISO-8601 UTC instant the window next frees capacity. For the rolling
   * session window this is when the oldest counted request ages out; for the
   * weekly window it is the next UTC-Monday reset. `null` when the (rolling)
   * window is empty and has nothing pending to reset. */
  resets_at: string | null;
}

/** AI request usage for the sidebar meter (`GET /ai/usage/me`).
 * Request counts only — the backend never exposes cost/token/provider data.
 * `blocked` mirrors the gateway gate: weekly exhaustion refuses new AI
 * requests with 409 QUOTA_EXCEEDED; the rolling session window is a soft warning. */
export interface AiUsageSummary {
  session: AiUsageWindow;
  week: AiUsageWindow;
  warning: boolean;
  blocked: boolean;
  blocked_scope: "session" | "week" | null;
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
  /** ISO-8601 UTC instant the weekly window resets. */
  week_reset: string;
  /** Number of days the breakdown/total cover (default 30). */
  window_days: number;
  /** Total AI requests in the window (includes system tasks not shown by feature). */
  total: number;
  by_feature: AiUsageFeatureCount[];
  recent: AiUsageActivity[];
}

export interface ChatAttachment {
  id: string;
  session_id: string;
  filename: string;
  content_type: string;
  size: number;
  status: string;
  created_at: string;
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

  /** Rename a chat session. */
  renameSession(sessionId: string, title: string): Promise<ChatSession> {
    return api.patch<ChatSession>(`/ai/chat/sessions/${sessionId}`, { title });
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

  /** Upload a file/image to a chat session for AI analysis (owner only). */
  async uploadAttachment(sessionId: string, file: File): Promise<ChatAttachment> {
    const form = new FormData();
    form.append("file", file);
    const res = await apiUpload<{ data: ChatAttachment }>(
      `/ai/chat/sessions/${sessionId}/attachments`,
      form,
    );
    return res.data;
  },

};
