import { api, apiFetch, apiUpload } from "./client";
import { ApiError } from "./errors";
import type { ApiEnvelope } from "./types";
import { env } from "@/lib/env";
import { getAccessToken } from "./session";

/**
 * AI mock-interview API client (`/api/v1/mock-interview/*`).
 *
 * Product/AI-safety notes:
 * - The coaching report is deliberately score-free: {@link CoachingReport} has
 *   no rating/percentage field and the UI must never derive one. Practice is
 *   advisory only (docs/AI_PRODUCT_SPEC — no hiring-probability guarantees).
 * - Provider/model/token internals are never surfaced. The optional realtime
 *   descriptor carries an ephemeral token only; no provider/model strings.
 * - Turn streaming mirrors the SSE reader used by the AI assistant chat window.
 */

export type MockInterviewModality = "voice" | "text" | "realtime";
export type MockInterviewSpeaker = "interviewer" | "candidate";
export type MockInterviewStatus =
  | "active"
  | "completed"
  | "aborted"
  | "expired";

/** Fit signal quality, mirroring the job-fit `signal` semantics. */
export type MockInterviewFitSignal = "ok" | "low_signal";

/* --------------------------------- prep ----------------------------------- */

export interface MockInterviewJobRef {
  id: string;
  title: string;
  company_name: string | null;
}

export interface MockInterviewPrepCv {
  cv_id: string;
  title: string;
  /** Deterministic product fit score (0–100). NOT an AI-confidence value. */
  score: number;
  is_recommended: boolean;
}

export interface MockInterviewPrep {
  job: MockInterviewJobRef;
  cvs: MockInterviewPrepCv[];
  recommended_cv_id: string | null;
  signal: MockInterviewFitSignal;
  /**
   * True when the true full-duplex realtime relay tier is available: the
   * student's mic audio streams to our server and the interviewer's native
   * audio streams back in real time (a live spoken conversation). This is the
   * PREFERRED voice tier — when set, create the session with
   * `modality: "realtime"` and drive it with the relay WebSocket client. No
   * provider/model identity is ever carried here.
   */
  realtime_relay?: boolean;
  /**
   * True when the server-mediated voice tier is available (the interviewer's
   * questions are narrated by AI and answers can be spoken and transcribed
   * server-side). When false, voice mode falls back to the browser voice tier
   * or text. Wire field is snake_case (`server_voice`); mirrors the rest of the
   * prep contract. No provider/model identity is ever carried here.
   */
  server_voice?: boolean;
  /**
   * Optional multi-round interview plan preview (screening → technical → …), so
   * the setup screen can show "what to expect" before starting. Defensive: when
   * the backend omits it the hero simply hides the plan. The authoritative plan
   * is returned again on create-session. No prompts/model identity carried here.
   */
  rounds?: MockInterviewRound[] | null;
  current_round?: string | number | null;
}

/* ------------------------------- sessions --------------------------------- */

export interface MockInterviewOpening {
  seq: number;
  speaker: MockInterviewSpeaker;
  text: string;
}

export interface MockInterviewCaps {
  max_session_seconds: number;
  max_questions: number;
  idle_timeout_seconds: number;
  target_questions: number;
}

/**
 * Realtime (V2) transport descriptor. Present only when the server has the
 * realtime path enabled (disabled by default). Transport-agnostic and carries
 * ONLY an ephemeral token — never a provider/model string or a durable key.
 */
export interface MockInterviewRealtimeDescriptor {
  transport: "websocket" | "webrtc";
  url: string;
  ephemeral_token: string;
  expires_at: string;
  duration_cap_s: number;
  turn_limit: number;
}

/**
 * Leak-safe interview-plan progress. Labels + counts only — never weights,
 * question ids, the question bank, tiers, or any score. `covered` are the
 * competencies already touched; `remaining` are still to cover. Rendered as a
 * subtle "topics" progress in the room and in the coaching report.
 */
export interface MockInterviewCoverage {
  total: number;
  covered_count: number;
  covered: string[];
  remaining: string[];
}

export type MockInterviewRoundStatus = "done" | "active" | "upcoming";

/**
 * One phase of a multi-round interview (e.g. screening → technical → behavioral).
 * Leak-safe: labels only — never a persona prompt, model, or score. Optional in
 * every contract; when absent the UI simply hides the round/phase indicator.
 */
export interface MockInterviewRound {
  id: string;
  label: string;
  /** Human-readable persona/style of this round (e.g. "Technical interview"). */
  persona_label?: string | null;
  status: MockInterviewRoundStatus;
}

export interface MockInterviewSession {
  session_id: string;
  modality: MockInterviewModality;
  locale: string;
  cv_id: string | null;
  opening: MockInterviewOpening;
  caps: MockInterviewCaps;
  realtime: MockInterviewRealtimeDescriptor | null;
  /**
   * Interview-plan topic coverage captured at session start (the opening
   * question's plan). Static during the live session — the SSE turn stream does
   * not currently re-emit coverage — so the room shows it as the interview PLAN,
   * and the coaching report shows the FINAL coverage from the session detail.
   */
  coverage?: MockInterviewCoverage | null;
  /**
   * Multi-round interview plan (screening → technical → behavioral …). Optional;
   * when present the live room shows a tasteful phase indicator. Absent → hidden.
   */
  rounds?: MockInterviewRound[] | null;
  /** Active round — the round `id` or a 0-based index. Advisory; `status` wins. */
  current_round?: string | number | null;
}

export interface MockInterviewTranscriptTurn {
  seq: number;
  speaker: MockInterviewSpeaker;
  text: string;
  created_at: string;
}

export interface CoachingReportQuestion {
  question: string;
  suggestion: string;
  observation: string;
}

/** A concrete next-step learning resource attached to a gap (leak-safe: no url
 *  internals required — `title` + a coarse `kind` badge only). */
export interface MockInterviewLearningSuggestion {
  title: string;
  /** Coarse resource kind, e.g. "course" | "article" | "video" | "practice". */
  kind?: string | null;
}

/**
 * A gap the student should work on. The backend may send a plain string (legacy)
 * or an object carrying attached learning suggestions. The UI normalizes both
 * via {@link normalizeGap}.
 */
export interface CoachingReportGap {
  text: string;
  learning?: MockInterviewLearningSuggestion[] | null;
}

/**
 * Score-free coaching output. There is intentionally NO `score`/`rating`/
 * `percentage` field — mock interview is formative practice, not assessment.
 */
export interface CoachingReport {
  per_question: CoachingReportQuestion[];
  overall_observations: string;
  /** Plain strings (legacy) or `{ text, learning[] }` objects. */
  gaps_to_work_on: Array<string | CoachingReportGap>;
  strengths: string[];
  prompt_version: number;
  is_fallback: boolean;
}

export interface MockInterviewSessionDetail {
  id: string;
  job_id: string;
  job_title?: string | null;
  cv_id: string | null;
  locale: string;
  modality: MockInterviewModality;
  status: MockInterviewStatus;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  question_count: number;
  has_report: boolean;
  created_at: string;
  share_opt_in: boolean;
  transcript: MockInterviewTranscriptTurn[];
  report: CoachingReport | null;
  /** Final interview-plan topic coverage (labels + counts only). */
  coverage?: MockInterviewCoverage | null;
  /** Interview phases the session ran through (all typically `done`). Optional. */
  rounds?: MockInterviewRound[] | null;
  current_round?: string | number | null;
}

/**
 * Compact row for the history list. `job_title`/`title` are both accepted for
 * resilience to the backend field name (assumption noted in the handoff).
 */
export interface MockInterviewSessionListItem {
  id: string;
  job_id: string;
  title?: string | null;
  job_title?: string | null;
  modality: MockInterviewModality;
  status: MockInterviewStatus;
  duration_seconds: number | null;
  question_count: number;
  has_report: boolean;
  created_at: string;
}

/* ------------------------------- progress --------------------------------- */

/**
 * A qualitative practice theme (a recurring gap or a strength). Deliberately
 * score-free: {@link count} is how many sessions surfaced the theme, and
 * {@link recurring} flags a theme the student keeps hitting — never a grade.
 */
export interface MockInterviewProgressTheme {
  text: string;
  count: number;
  recurring: boolean;
}

/**
 * Cross-session practice progress for the student "My interviews" surface.
 * Formative and qualitative only — there is intentionally NO score/rating.
 * `by_focus` is a sparse map keyed by focus area (e.g. technical/behavioral/
 * mixed); `recent` mirrors the compact history row shape.
 */
export interface MockInterviewProgress {
  completed: number;
  recurring_gaps: MockInterviewProgressTheme[];
  top_strengths: MockInterviewProgressTheme[];
  by_focus: Record<string, number>;
  recent: MockInterviewSessionListItem[];
}

/* ---------------------------- admin / oversight --------------------------- */

/** One day of the oversight activity trend (aggregate count only). */
export interface MockInterviewTrendPoint {
  date: string;
  count: number;
}

/** A most-practiced job row for oversight. `title` may be null (job removed). */
export interface MockInterviewTopJob {
  job_id: string;
  title: string | null;
  count: number;
}

/**
 * University oversight aggregate for the mock-interview feature. Aggregate-only:
 * carries NO student PII and NO provider/model internals. `by_modality` and
 * `by_focus` are sparse maps; `trend` is per-day and `top_jobs` is ranked.
 */
export interface MockInterviewAdminStats {
  total: number;
  completed: number;
  aborted: number;
  active: number;
  flagged: number;
  avg_questions: number;
  avg_duration_seconds: number;
  distinct_students: number;
  by_modality: Partial<Record<MockInterviewModality, number>>;
  /** 0–1 completion ratio (completed / total). */
  completion_rate: number;
  window_days: number;
  /** Per-day session counts across the window (oldest → newest). */
  trend: MockInterviewTrendPoint[];
  /** Ranked most-practiced jobs in the window. */
  top_jobs: MockInterviewTopJob[];
  /** Sparse focus-area distribution (technical/behavioral/mixed/…). */
  by_focus: Record<string, number>;
}

/**
 * Read-only effective limits for the feature. Deliberately provider/model-free:
 * only caps and the realtime toggle — never any AI backend identity.
 */
export interface MockInterviewAdminConfig {
  daily_session_cap: number;
  weekly_session_cap: number;
  max_session_seconds: number;
  max_questions: number;
  target_questions: number;
  realtime_voice_enabled: boolean;
}

/** A compact flagged-session row for the superadmin safety review list. */
export interface MockInterviewFlaggedItem {
  session_id: string;
  job_id: string;
  modality: MockInterviewModality;
  status: MockInterviewStatus;
  question_count: number;
  share_opt_in: boolean;
  created_at: string;
}

export type MockInterviewAdminTranscriptMode = "redacted" | "full";

/** Audited transcript view. `mode` states whether PII is pseudonymized. */
export interface MockInterviewAdminTranscript {
  session_id: string;
  mode: MockInterviewAdminTranscriptMode;
  flagged: boolean;
  modality: MockInterviewModality;
  status: MockInterviewStatus;
  report: CoachingReport | null;
  transcript: MockInterviewOpening[];
}

/* ------------------------------- requests --------------------------------- */

export interface CreateMockInterviewBody {
  job_id: string;
  cv_id?: string | null;
  modality: MockInterviewModality;
  locale: string;
}

export interface RecordTurnInput {
  speaker: MockInterviewSpeaker;
  text: string;
}

export interface RecordTurnsResult {
  added: number;
  question_count: number;
}

export interface EndSessionBody {
  duration_seconds?: number;
  turns?: RecordTurnInput[];
}

/* ------------------------------ SSE streaming ----------------------------- */

/** A single interviewer token chunk. */
export interface TurnTokenEvent {
  type: "token";
  text: string;
}

/** Terminal event once the interviewer's reply is fully generated. */
export interface TurnDoneEvent {
  type: "done";
  seq: number;
  text: string;
  question_count: number;
  ended: boolean;
  /** Live topic coverage after this turn (leak-safe summary), so the room's
   * coverage chips advance per turn. Absent on early-end/conflict paths. */
  coverage?: MockInterviewCoverage | null;
  /**
   * Optional advisory coaching nudge for the answer just given (e.g. "try adding
   * a concrete metric"). Rendered as a calm, dismissible chip that clears on the
   * next turn. Never blocking; absent/null → nothing shown.
   */
  nudge?: { text: string } | null;
}

export interface TurnErrorEvent {
  type: "error";
  code: string;
}

export type TurnStreamEvent = TurnTokenEvent | TurnDoneEvent | TurnErrorEvent;

export interface StreamTurnHandlers {
  /** Called for each interviewer token as it arrives. */
  onToken?: (text: string) => void;
  /** Called once the interviewer reply is complete. */
  onDone?: (event: TurnDoneEvent) => void;
  /** Called on a server-side error event or transport failure. */
  onError?: (code: string) => void;
}

/* --------------------------------- client --------------------------------- */

export const mockInterviewApi = {
  /** CV picker + deterministic fit for the setup screen. */
  prep(jobId: string, locale: string): Promise<MockInterviewPrep> {
    return api.get<MockInterviewPrep>("/mock-interview/prep", {
      query: { job_id: jobId, locale },
    });
  },

  /** Start a session. Returns the opening line, caps, and (rarely) a realtime
   *  descriptor. The server decides modality; it may downgrade a request. */
  createSession(body: CreateMockInterviewBody): Promise<MockInterviewSession> {
    return api.post<MockInterviewSession>("/mock-interview/sessions", body);
  },

  /**
   * Stream one candidate turn over SSE. Mirrors the AI-assistant chat reader:
   * `data: {json}` lines with `token` chunks then a `done` (or `error`) event.
   * Resolves when the stream ends; rejects/`onError` on transport failure.
   */
  async streamTurn(
    sessionId: string,
    answer: string,
    handlers: StreamTurnHandlers,
    signal?: AbortSignal,
  ): Promise<void> {
    const base = env.apiBaseUrl.replace(/\/$/, "");
    const url = `${base}/mock-interview/sessions/${sessionId}/turns/stream`;
    const token = getAccessToken();

    let res: Response;
    try {
      res = await fetch(url, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ answer }),
        signal,
      });
    } catch {
      handlers.onError?.("NETWORK_ERROR");
      return;
    }

    if (!res.ok || !res.body) {
      handlers.onError?.(res.status === 409 ? "CONFLICT" : "AI_UNAVAILABLE");
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const jsonStr = line.slice(6).trim();
          if (!jsonStr) continue;

          let event: TurnStreamEvent;
          try {
            event = JSON.parse(jsonStr) as TurnStreamEvent;
          } catch {
            continue;
          }

          if (event.type === "token") {
            handlers.onToken?.(event.text);
          } else if (event.type === "done") {
            handlers.onDone?.(event);
            return;
          } else if (event.type === "error") {
            handlers.onError?.(event.code);
            return;
          }
        }
      }
    } catch {
      // Aborted (user ended) or a mid-stream read failure.
      if (!signal?.aborted) handlers.onError?.("NETWORK_ERROR");
      return;
    }
  },

  /**
   * Server-mediated TTS for the voice tier. POSTs `{ text, voice? }` and reads
   * the response as raw `audio/wav` bytes (NOT a JSON envelope — hence a raw
   * fetch rather than {@link api.post}). Any non-audio response (a JSON error
   * envelope, e.g. `AIUnavailable`, or a transport failure) is surfaced as an
   * {@link ApiError} so callers can degrade to captions/text. No provider,
   * model, or token internals are ever exposed.
   */
  async synthesizeSpeech(
    sessionId: string,
    text: string,
    voice?: string,
  ): Promise<Blob> {
    const base = env.apiBaseUrl.replace(/\/$/, "");
    const url = `${base}/mock-interview/sessions/${sessionId}/tts`;
    const token = getAccessToken();

    let res: Response;
    try {
      res = await fetch(url, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          Accept: "audio/wav, application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(voice ? { text, voice } : { text }),
      });
    } catch {
      throw new ApiError({
        code: "NETWORK_ERROR",
        message: "Unable to reach the voice service.",
        status: 0,
      });
    }

    const contentType = (res.headers.get("content-type") ?? "").toLowerCase();
    if (res.ok && contentType.startsWith("audio/")) {
      return res.blob();
    }

    // Non-audio → treat as "voice unavailable". Best-effort read the user-safe
    // message from the JSON error envelope; never leak internal codes.
    let message = "Voice is temporarily unavailable.";
    try {
      const body = (await res.json()) as {
        error?: { message?: string };
        message?: string;
      };
      message = body?.error?.message ?? body?.message ?? message;
    } catch {
      // Non-JSON / empty body — keep the generic message.
    }
    throw new ApiError({
      code: "AI_UNAVAILABLE",
      message,
      status: res.status,
    });
  },

  /**
   * Server-mediated STT for the voice tier. Uploads the recorded answer blob as
   * multipart/form-data (single `audio` field) and returns the transcript for
   * the student to REVIEW and edit before submitting a turn — never auto-sent.
   * Failures surface as an {@link ApiError} (e.g. `SPEECH_UNAVAILABLE`).
   */
  async transcribeAnswer(
    sessionId: string,
    audio: Blob,
  ): Promise<{ transcript: string }> {
    const form = new FormData();
    form.append("audio", audio, recorderFileName(audio.type));
    const res = await apiUpload<ApiEnvelope<{ transcript: string }>>(
      `/mock-interview/sessions/${sessionId}/stt`,
      form,
    );
    return res.data;
  },

  /** Flush realtime (V2) turns captured client-side. */
  recordTurns(
    sessionId: string,
    turns: RecordTurnInput[],
  ): Promise<RecordTurnsResult> {
    return api.post<RecordTurnsResult>(
      `/mock-interview/sessions/${sessionId}/turns`,
      { turns },
    );
  },

  /** End a session and receive the full detail (incl. coaching report). */
  endSession(
    sessionId: string,
    body: EndSessionBody = {},
  ): Promise<MockInterviewSessionDetail> {
    return api.post<MockInterviewSessionDetail>(
      `/mock-interview/sessions/${sessionId}/end`,
      body,
    );
  },

  /** Abort an in-progress session (no report). Tolerates 204/enveloped. */
  async abortSession(sessionId: string): Promise<void> {
    await apiFetch(`/mock-interview/sessions/${sessionId}/abort`, {
      method: "POST",
      json: {},
    });
  },

  /** Opt in/out of sharing this transcript to improve the AI. */
  async shareSession(sessionId: string, optIn: boolean): Promise<void> {
    await apiFetch(`/mock-interview/sessions/${sessionId}/share`, {
      method: "POST",
      json: { opt_in: optIn },
    });
  },

  /** Permanently delete a session and its transcript. */
  async deleteSession(sessionId: string): Promise<void> {
    await apiFetch(`/mock-interview/sessions/${sessionId}`, {
      method: "DELETE",
    });
  },

  /** Recent sessions for the history list. */
  listSessions(limit?: number): Promise<MockInterviewSessionListItem[]> {
    return api.get<MockInterviewSessionListItem[]>(
      "/mock-interview/sessions",
      limit ? { query: { limit } } : undefined,
    );
  },

  /** Full detail for one session (transcript + report). */
  getSession(sessionId: string): Promise<MockInterviewSessionDetail> {
    return api.get<MockInterviewSessionDetail>(
      `/mock-interview/sessions/${sessionId}`,
    );
  },

  /**
   * Cross-session, score-free practice progress: completed count, recurring
   * gaps/strengths, focus mix, and recent sessions. Powers the student
   * "My interviews" progress summary.
   */
  getProgress(): Promise<MockInterviewProgress> {
    return api.get<MockInterviewProgress>("/mock-interview/progress");
  },

  /* --- university oversight (university-only; enforced server-side) --- */

  /** Aggregate usage + safety stats over a trailing window (days). */
  adminStats(days = 30): Promise<MockInterviewAdminStats> {
    return api.get<MockInterviewAdminStats>("/admin/mock-interview/stats", {
      query: { days },
    });
  },

  /** Read-only effective limits for the feature (provider/model-free). */
  adminConfig(): Promise<MockInterviewAdminConfig> {
    return api.get<MockInterviewAdminConfig>("/admin/mock-interview/config");
  },

  /** Superadmin-only: sessions flagged for safety review. */
  adminFlagged(limit = 50): Promise<MockInterviewFlaggedItem[]> {
    return api.get<MockInterviewFlaggedItem[]>(
      "/admin/mock-interview/flagged",
      { query: { limit } },
    );
  },

  /** Superadmin-only: audited (pseudonymized-by-default) transcript + report. */
  adminTranscript(sessionId: string): Promise<MockInterviewAdminTranscript> {
    return api.get<MockInterviewAdminTranscript>(
      `/admin/mock-interview/sessions/${sessionId}/transcript`,
    );
  },
};

/** Map a recorded-blob MIME type to a stable multipart filename (cosmetic). */
function recorderFileName(mime: string): string {
  const m = mime.toLowerCase();
  if (m.includes("mp4") || m.includes("m4a")) return "answer.m4a";
  if (m.includes("mpeg") || m.includes("mp3")) return "answer.mp3";
  if (m.includes("ogg")) return "answer.ogg";
  if (m.includes("wav")) return "answer.wav";
  return "answer.webm";
}

/** Best available display title for a history row. */
export function sessionListTitle(item: MockInterviewSessionListItem): string {
  return item.title ?? item.job_title ?? "";
}

/** Best available display title for a most-practiced job row (never a raw key). */
export function topJobTitle(item: MockInterviewTopJob): string {
  const title = item.title?.trim();
  if (title) return title;
  return `#${item.job_id.slice(0, 8)}`;
}

/** A gap normalized to `{ text, learning[] }` regardless of the wire shape. */
export interface NormalizedGap {
  text: string;
  learning: MockInterviewLearningSuggestion[];
}

/**
 * Accepts either the legacy plain-string gap or the `{ text, learning }` object
 * and returns a stable shape. Learning entries missing a title are dropped so
 * the UI never renders an empty chip.
 */
export function normalizeGap(item: string | CoachingReportGap): NormalizedGap {
  if (typeof item === "string") return { text: item, learning: [] };
  const text = typeof item?.text === "string" ? item.text : "";
  const learning = Array.isArray(item?.learning)
    ? item.learning.filter(
        (l): l is MockInterviewLearningSuggestion =>
          !!l && typeof l.title === "string" && l.title.trim().length > 0,
      )
    : [];
  return { text, learning };
}

/** Derived, render-ready multi-round plan. */
export interface RoundPlan {
  rounds: MockInterviewRound[];
  /** 0-based index of the active (or, in a finished report, final) round. */
  activeIndex: number;
  total: number;
}

/**
 * Normalize the optional `rounds` + `current_round` contract into a render-ready
 * plan. Returns `null` when no usable rounds are present so callers can hide the
 * phase indicator entirely. Prefers a round with `status: "active"`; falls back
 * to `current_round` (id or index), then to the round after the last `done`.
 */
export function deriveRoundPlan(
  rounds: MockInterviewRound[] | null | undefined,
  current?: string | number | null,
): RoundPlan | null {
  if (!Array.isArray(rounds) || rounds.length === 0) return null;
  const clean = rounds.filter(
    (r): r is MockInterviewRound =>
      !!r && typeof r.id === "string" && typeof r.label === "string" && r.label.trim().length > 0,
  );
  if (clean.length === 0) return null;

  let activeIndex = clean.findIndex((r) => r.status === "active");
  if (activeIndex === -1 && current != null) {
    activeIndex =
      typeof current === "number"
        ? current
        : clean.findIndex((r) => r.id === current);
  }
  if (activeIndex === -1) {
    // No explicit active round → the one after the last completed round.
    let lastDone = -1;
    clean.forEach((r, i) => {
      if (r.status === "done") lastDone = i;
    });
    activeIndex = Math.min(lastDone + 1, clean.length - 1);
  }
  activeIndex = Math.max(0, Math.min(activeIndex, clean.length - 1));
  return { rounds: clean, activeIndex, total: clean.length };
}
