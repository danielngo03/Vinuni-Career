import { api } from "./client";

export interface TalentCard {
  profile_id: string;
  display_name: string;
  avatar_url: string | null;
  headline: string | null;
  major: string | null;
  degree_level: string | null;
  degree_level_label: string | null;
  graduation_year: number | null;
  location_city: string | null;
  location_country: string | null;
  open_to_work_types: string[];
  open_to_work_type_labels: string[];
  profile_completion: number;
  updated_at: string | null;
}

export interface TalentPage {
  items: TalentCard[];
  page: {
    total: number | null;
    limit: number;
    next_cursor: string | null;
  };
}

export interface TalentSearchParams {
  open_to_work_type?: string;
  degree_level?: string;
  keyword?: string;
  cursor?: string;
  limit?: number;
}

export const talentPoolApi = {
  search(params: TalentSearchParams = {}): Promise<TalentPage> {
    const qs = new URLSearchParams();
    if (params.open_to_work_type) qs.set("open_to_work_type", params.open_to_work_type);
    if (params.degree_level) qs.set("degree_level", params.degree_level);
    if (params.keyword) qs.set("keyword", params.keyword);
    if (params.cursor) qs.set("cursor", params.cursor);
    if (params.limit) qs.set("limit", String(params.limit));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return api.get<TalentPage>(`/students/talent${suffix}`);
  },
};
