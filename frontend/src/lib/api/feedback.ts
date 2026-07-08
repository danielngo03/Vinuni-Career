import { api } from "./client";

export interface FeedbackBody {
  category: "bug" | "suggestion" | "praise" | "other";
  message: string;
  page_url?: string;
}

export interface FeedbackResult {
  id: string;
  created_at: string;
}

export const feedbackApi = {
  submit(body: FeedbackBody): Promise<FeedbackResult> {
    return api.post<FeedbackResult>("/feedback", body);
  },
};
