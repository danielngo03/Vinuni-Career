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
}

export interface AnswerFeedbackResult {
  score: number;
  praise: string;
  improve: string;
  hint: string;
  prompt_version: number;
  is_fallback: boolean;
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
