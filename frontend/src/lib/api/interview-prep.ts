import { api } from "./client";

export interface InterviewQuestion {
  number: number;
  type: "behavioral" | "technical" | "situational" | "motivation";
  question: string;
  hint: string;
  rubric: string;
}

export interface InterviewPrepResult {
  questions: InterviewQuestion[];
  prep_tips: string;
  prompt_version: number;
  is_fallback: boolean;
  /**
   * Durable id of the persisted practice attempt. Threaded into every
   * subsequent `answer-feedback` call so answers attach to this same attempt
   * (and roll up into the deterministic readiness signal).
   */
  session_id: string;
}

export interface InterviewPrepRequest {
  num_questions?: number;
  student_instruction?: string;
}

export interface AnswerFeedbackRequest {
  question: string;
  question_type: InterviewQuestion["type"];
  rubric: string;
  answer: string;
  /** Practice attempt this answer belongs to (from the prep response). */
  session_id?: string;
  /** Question index within the attempt. */
  question_number?: number;
}

export interface AnswerFeedbackResult {
  score: number;
  praise: string;
  improve: string;
  hint: string;
  prompt_version: number;
  is_fallback: boolean;
}

/**
 * Deterministic, HONEST interview-readiness signal derived from the student's
 * own practice history. Below `MIN_ANSWERS_FOR_SIGNAL` evaluated answers the
 * backend returns `status: "not_enough_data"` with `readiness_pct: null` — we
 * never fabricate a number from too little practice. No provider/model/token
 * internals ever appear here (scores are the 1-5 coaching scores only).
 */
export interface InterviewReadiness {
  status: "ready_signal" | "not_enough_data";
  attempts: number;
  answers_evaluated: number;
  readiness_pct: number | null;
  band: "developing" | "emerging" | "progressing" | "interview_ready" | null;
  trend: "improving" | "steady" | "declining" | null;
  /** How many more evaluated answers are needed before a readiness % is shown. */
  answers_needed: number;
}

/** One past practice attempt (question set) in the student's own history. */
export interface InterviewAttempt {
  id: string;
  job_id: string | null;
  job_title: string | null;
  questions_count: number;
  answered_count: number;
  avg_score: number | null;
  created_at: string | null;
  updated_at: string | null;
}

/** `GET /jobs/interview-sim/history` — my readiness + recent attempts. */
export interface InterviewHistory {
  readiness: InterviewReadiness;
  sessions: InterviewAttempt[];
}

/** One answered turn within a past attempt (owner-only). */
export interface InterviewTurn {
  id: string;
  question_number: number;
  question_type: string;
  question: string;
  rubric: string | null;
  answer: string;
  score: number | null;
  praise: string | null;
  improve: string | null;
  hint: string | null;
  is_fallback: boolean;
  created_at: string | null;
}

/** `GET /jobs/interview-sim/history/{id}` — one attempt with its turns. */
export interface InterviewSessionDetail {
  session: InterviewAttempt;
  turns: InterviewTurn[];
}

export const interviewPrepApi = {
  generatePrep(
    jobId: string,
    body: InterviewPrepRequest = {},
  ): Promise<InterviewPrepResult> {
    return api.post<InterviewPrepResult>(
      `/jobs/${jobId}/ai-interview-prep`,
      body,
    );
  },

  getAnswerFeedback(
    jobId: string,
    body: AnswerFeedbackRequest,
  ): Promise<AnswerFeedbackResult> {
    return api.post<AnswerFeedbackResult>(
      `/jobs/${jobId}/interview-sim/answer-feedback`,
      body,
    );
  },

  /** My interview practice history + deterministic readiness signal (student). */
  getHistory(): Promise<InterviewHistory> {
    return api.get<InterviewHistory>("/jobs/interview-sim/history");
  },

  /** One owned practice attempt with its answered turns (student). */
  getSessionDetail(sessionId: string): Promise<InterviewSessionDetail> {
    return api.get<InterviewSessionDetail>(
      `/jobs/interview-sim/history/${sessionId}`,
    );
  },
};

export interface CoverLetterResult {
  draft: string;
  prompt_version: number;
  is_fallback: boolean;
}

export interface CoverLetterRequest {
  student_note?: string;
}

export const coverLetterApi = {
  generate(
    jobId: string,
    body: CoverLetterRequest = {},
  ): Promise<CoverLetterResult> {
    return api.post<CoverLetterResult>(
      `/jobs/${jobId}/ai-cover-letter`,
      body,
    );
  },
};
