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

/** User decision for a pending tool action. */
export type ToolDecision = "confirm" | "cancel";

/* --------------------- Student render-artifact schemas --------------------- */
/* FROZEN contracts (student-ai-power design §3). The backend emits these on the
 * assistant message `tool_result.artifacts[]`; the chat UI renders them as
 * structured cards. No provider/model/token internals ever ride on an artifact. */

/** One skill with an optional 0-100 proficiency level. */
export interface CvSkillRef {
  name: string;
  level: number | null;
}

/** `cv_card` — an in-chat summary of one of the student's CVs. */
export interface CvCardArtifact {
  kind: "cv_card";
  cv_id: string;
  title: string;
  source: "uploaded" | "template";
  updated_at: string;
  is_default: boolean;
  summary: string | null;
  top_skills: CvSkillRef[];
  experience_count: number;
  education_count: number;
  /** Deep link to view the CV, e.g. `/student/cv/{cv_id}`. */
  view_path: string;
}

/** One matched job in a `job_match_list`. */
export interface JobMatchItem {
  job_id: string;
  title: string;
  company_name: string | null;
  location: string | null;
  fit_score: number | null;
  /** Band label (never a raw score noun). Localized via `fitBands.*` when known. */
  fit_band: string | null;
  top_reasons: string[];
  deadline: string | null;
  is_saved: boolean;
  view_path: string;
}

/** `job_match_list` — a grid of JD match cards ranked against one CV. */
export interface JobMatchListArtifact {
  kind: "job_match_list";
  cv_id: string;
  cv_title: string;
  total: number;
  items: JobMatchItem[];
}

/** One job column header in a `job_compare` table. */
export interface JobCompareColumn {
  job_id: string;
  title: string;
  company_name: string | null;
  view_path: string;
}

/** One aligned comparison row: one value per job column. */
export interface JobCompareRow {
  label_key: string;
  values: (string | number | null)[];
}

/** `job_compare` — side-by-side comparison of 2-4 jobs. */
export interface JobCompareArtifact {
  kind: "job_compare";
  cv_id: string | null;
  jobs: JobCompareColumn[];
  rows: JobCompareRow[];
}

export interface MatchedSkillRef {
  name: string;
  evidence: string | null;
}

export interface MissingSkillRef {
  name: string;
  importance: "high" | "medium" | "low";
}

/** A fit suggestion, optionally deep-linking into CV-Studio for a CV. */
export interface FitSuggestion {
  text: string;
  action: { kind: "cv_studio"; cv_id: string } | null;
}

/** `fit_breakdown` — deterministic CV↔job fit explanation. */
export interface FitBreakdownArtifact {
  kind: "fit_breakdown";
  job_id: string;
  job_title: string;
  company_name: string | null;
  cv_id: string;
  cv_title: string;
  fit_score: number | null;
  fit_band: string | null;
  matched_skills: MatchedSkillRef[];
  missing_skills: MissingSkillRef[];
  strengths: string[];
  gaps: string[];
  suggestions: FitSuggestion[];
}

/** One CV row in a `cv_compare`. */
export interface CvCompareItem {
  cv_id: string;
  title: string;
  fit_score: number | null;
  fit_band: string | null;
  highlight: string | null;
  view_path: string;
}

/** `cv_compare` — which of the student's CVs is strongest (overall or for a job). */
export interface CvCompareArtifact {
  kind: "cv_compare";
  job_id: string | null;
  job_title: string | null;
  cvs: CvCompareItem[];
  recommended_cv_id: string | null;
}

/** One selectable CV chip in a `cv_picker`. */
export interface CvPickerOption {
  cv_id: string;
  title: string;
  source: string;
  updated_at: string;
  is_default: boolean;
}

/** `cv_picker` — clarifying CV selection (NOT a mutation confirmation). Clicking
 * a chip re-issues the pending tool turn with the chosen `cv_id`. */
export interface CvPickerArtifact {
  kind: "cv_picker";
  prompt_key: string;
  pending_tool: string;
  pending_args: Record<string, unknown>;
  cvs: CvPickerOption[];
}

export interface CareerFocusCluster {
  label: string;
  why: string;
  example_job_ids: string[];
}

export interface CareerTopMatch {
  job_id: string;
  title: string;
  fit_band: string;
}

export interface CareerSkillPriority {
  skill: string;
  impact: string;
}

/** `career_brief` — deep multi-signal career narrative (workforce agent output). */
export interface CareerBriefArtifact {
  kind: "career_brief";
  generated_at: string;
  focus_clusters: CareerFocusCluster[];
  top_matches: CareerTopMatch[];
  skill_priorities: CareerSkillPriority[];
  summary: string;
}

/** Union of all student render artifacts (§3). */
export type StudentRenderArtifact =
  | CvCardArtifact
  | JobMatchListArtifact
  | JobCompareArtifact
  | FitBreakdownArtifact
  | CvCompareArtifact
  | CvPickerArtifact
  | CareerBriefArtifact;

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

  /** Confirm (execute) or cancel a pending tool action. Cancel resolves with
   * `confirmed: false` plus the assistant's follow-up reply. */
  confirmToolAction(
    sessionId: string,
    messageId: string,
    decision: ToolDecision = "confirm",
  ): Promise<{ confirmed: ChatMessage | false; reply: ChatMessage }> {
    return api.post<{ confirmed: ChatMessage | false; reply: ChatMessage }>(
      `/ai/chat/sessions/${sessionId}/messages/${messageId}/confirm`,
      { decision },
    );
  },

  /** Edit a user message; the server truncates later turns and re-runs. The
   * caller should refetch the whole thread afterwards. */
  editMessage(
    sessionId: string,
    messageId: string,
    text: string,
  ): Promise<{ reply: ChatMessage }> {
    return api.patch<{ reply: ChatMessage }>(
      `/ai/chat/sessions/${sessionId}/messages/${messageId}`,
      { text },
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
