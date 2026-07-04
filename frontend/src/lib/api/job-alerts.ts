import { api } from "./client";

export interface JobAlert {
  id: string;
  name: string;
  keywords: string | null;
  employment_type: string | null;
  location_type: string | null;
  province_code: string | null;
  is_active: boolean;
  last_sent_at: string | null;
  created_at: string;
}

export interface CreateJobAlertBody {
  name: string;
  keywords?: string | null;
  employment_type?: string | null;
  location_type?: string | null;
  province_code?: string | null;
}

export const jobAlertsApi = {
  list(): Promise<JobAlert[]> {
    return api.get<JobAlert[]>("/jobs/alerts");
  },

  create(body: CreateJobAlertBody): Promise<JobAlert> {
    return api.post<JobAlert>("/jobs/alerts", body);
  },

  delete(alertId: string): Promise<{ status: string }> {
    return api.delete<{ status: string }>(`/jobs/alerts/${alertId}`);
  },
};
