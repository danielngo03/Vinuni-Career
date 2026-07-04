import { api, apiFetch } from "./client";

export interface PopularKeywordsResponse {
  keywords: string[];
}

export interface IndustryLeaf {
  id: string;
  slug: string;
  name_vi: string;
  name_en: string;
  level: number;
  sort_order: number;
}

export interface IndustryBranch extends IndustryLeaf {
  children: IndustryLeaf[];
}

export interface IndustryRoot extends IndustryLeaf {
  children: IndustryBranch[];
}

export const searchApi = {
  log(query: string, locale: string): Promise<void> {
    return api.post<void>("/search/log", { query, locale }, { skipAuth: true });
  },
  popular(locale: string, limit = 8): Promise<PopularKeywordsResponse> {
    return api.get<PopularKeywordsResponse>(
      `/search/popular?locale=${encodeURIComponent(locale)}&limit=${limit}`,
      { skipAuth: true },
    );
  },
  industryTree(): Promise<IndustryRoot[]> {
    return apiFetch<IndustryRoot[]>("/industries", {
      method: "GET",
      skipAuth: true,
    });
  },
};
