/**
 * Career-outcomes university read API (`/api/v1/career-outcomes`).
 *
 * The backend table holds no student PII and no salary; this surface returns
 * aggregate KPIs and a privacy-safe record list with friendly (already
 * localized) trust/outcome labels — never raw enum codes.
 */
import { api } from "./client";

export interface CareerOutcomeTrustBucket {
  trust_level: number;
  label: string;
  count: number;
}

export interface CareerOutcomeEmployer {
  employer_name: string;
  count: number;
}

export interface CareerOutcomeRecord {
  id: string;
  position_title: string | null;
  employer_name: string;
  start_date: string | null;
  outcome: string;
  trust_label: string;
  recorded_at: string | null;
}

export interface CareerOutcomeKpi {
  total_outcomes: number;
  by_trust_level: CareerOutcomeTrustBucket[];
  top_employers: CareerOutcomeEmployer[];
  recent: CareerOutcomeRecord[];
}

export interface CareerOutcomeRecords {
  items: CareerOutcomeRecord[];
  count: number;
}

export const careerOutcomesApi = {
  getKpi(locale: string): Promise<CareerOutcomeKpi> {
    return api.get<CareerOutcomeKpi>("/career-outcomes/kpi", {
      query: { locale },
    });
  },
  listRecords(locale: string, trustLevel?: number): Promise<CareerOutcomeRecords> {
    return api.get<CareerOutcomeRecords>("/career-outcomes/records", {
      query: {
        locale,
        ...(trustLevel != null ? { trust_level: trustLevel } : {}),
      },
    });
  },
};
