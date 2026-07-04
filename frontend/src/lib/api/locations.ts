/**
 * Vietnamese provinces / wards reference data API.
 *
 * Used by multi-location job pickers and (future) map-based discovery.
 * These endpoints are public and require no auth.
 */
import { apiFetch } from "./client";

export interface Province {
  code: string;
  name: string;
  full_name: string;
  slug: string;
  /** "city" | "province" */
  type: string;
  is_central: boolean;
}

export interface Ward {
  code: string;
  name: string;
  full_name: string;
  slug: string;
  /** "ward" | "commune" */
  type: string;
}

export const locationsApi = {
  listProvinces(): Promise<{ items: Province[] }> {
    return apiFetch<{ items: Province[] }>("/locations/provinces", { method: "GET" });
  },

  listWards(provinceCode: string): Promise<{ items: Ward[] }> {
    return apiFetch<{ items: Ward[] }>(`/locations/provinces/${provinceCode}/wards`, { method: "GET" });
  },
};
