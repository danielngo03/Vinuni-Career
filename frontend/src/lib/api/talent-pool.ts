import { api } from "./client";

/**
 * Passive talent-pool result card (`GET /students/talent`).
 *
 * Owner decision (2026-07-06): student profiles are identity-only — all career
 * content lives in CVs, accessed through the recruitment reveal handshake. So a
 * talent card carries NO skills/experience/degree; it is a blind-screening
 * signal only: an anonymised handle, coarse location, the open-to-work flag, and
 * freshness. For external partner recruiters the backend masks identity entirely
 * (`identity_masked: true`) — no real name, no photo — replacing the name with a
 * stable `UV-xxxx` handle. University staff / superadmins see the identified view.
 */
export interface TalentCard {
  profile_id: string;
  /** Real full name, OR the opaque `UV-xxxx` handle when `identity_masked`. */
  display_name: string;
  /** The stable masked handle (present only in the masked/blind-screening view). */
  anonymous_id?: string | null;
  /** Safe avatar URL — always `null` in the masked view. */
  avatar_url: string | null;
  /** Whether this card is anonymised (blind screening) for the caller. */
  identity_masked: boolean;
  location_city: string | null;
  location_country: string | null;
  is_open_to_work: boolean;
  /** Signal freshness (profile last updated); drives the "open X ago" hint. */
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

/**
 * Search params. The backend matches `keyword` against coarse location
 * (city/country) only — career filters were removed with the identity-only
 * profile model, so we deliberately do not send non-functional degree/work-type
 * filters here (no fake filters).
 */
export interface TalentSearchParams {
  keyword?: string;
  cursor?: string;
  limit?: number;
}

export const talentPoolApi = {
  search(params: TalentSearchParams = {}): Promise<TalentPage> {
    const qs = new URLSearchParams();
    if (params.keyword) qs.set("keyword", params.keyword);
    if (params.cursor) qs.set("cursor", params.cursor);
    if (params.limit) qs.set("limit", String(params.limit));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return api.get<TalentPage>(`/students/talent${suffix}`);
  },
};
