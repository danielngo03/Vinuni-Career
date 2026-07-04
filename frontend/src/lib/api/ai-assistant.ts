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

export const aiAssistantApi = {
  /** My AI usage today vs the daily allowance. */
  myUsage(): Promise<AiUsageSummary> {
    return api.get<AiUsageSummary>("/ai/usage/me");
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
