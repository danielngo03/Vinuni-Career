import { api, apiFetch } from "./client";
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

export interface MockInterviewSession {
  session_id: string;
  modality: MockInterviewModality;
  locale: string;
  cv_id: string | null;
  opening: MockInterviewOpening;
  caps: MockInterviewCaps;
  realtime: MockInterviewRealtimeDescriptor | null;
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

/**
 * Score-free coaching output. There is intentionally NO `score`/`rating`/
 * `percentage` field — mock interview is formative practice, not assessment.
 */
export interface CoachingReport {
  per_question: CoachingReportQuestion[];
  overall_observations: string;
  gaps_to_work_on: string[];
  strengths: string[];
  prompt_version: number;
  is_fallback: boolean;
}

export interface MockInterviewSessionDetail {
  id: string;
  job_id: string;
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
};

/** Best available display title for a history row. */
export function sessionListTitle(item: MockInterviewSessionListItem): string {
  return item.title ?? item.job_title ?? "";
}
