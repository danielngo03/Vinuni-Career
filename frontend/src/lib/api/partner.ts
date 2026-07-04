import { api } from "./client";

/* ------------------------------- Wire types ------------------------------- */

export interface PartnerRegistrationBody {
  company_name: string;
  tax_code?: string | null;
  company_website?: string | null;
  company_size?: string | null;
  industry?: string | null;
  description?: string | null;
  contact_name: string;
  contact_title?: string | null;
  email: string;
  phone?: string | null;
  logo_upload_id?: string | null;
}

export interface PartnerRegistrationResult {
  registration_id: string;
  status: string;
}

/** Admin review row (GET /admin/partners). */
export interface PartnerRegistration {
  id: string;
  company_name: string;
  industry?: string | null;
  company_size?: string | null;
  contact_name: string;
  contact_email: string;
  contact_title?: string | null;
  status: string;
  status_label: string;
  review_note?: string | null;
  created_org_id?: string | null;
  version: number;
  created_at: string;
}

export type TrustLevel = "standard" | "verified" | "strategic";

/* --------------------------------- Calls ---------------------------------- */

export const partnerApi = {
  /** Public self-registration. Caller supplies a client-generated Idempotency-Key. */
  register(
    body: PartnerRegistrationBody,
    idempotencyKey: string,
  ): Promise<PartnerRegistrationResult> {
    return api.post<PartnerRegistrationResult>("/partner-registration", body, {
      skipAuth: true,
      headers: { "Idempotency-Key": idempotencyKey },
    });
  },

  /** University review queue. `status` filters by registration status. */
  listRegistrations(status?: string): Promise<PartnerRegistration[]> {
    return api.get<PartnerRegistration[]>("/admin/partners", {
      query: status ? { status } : undefined,
    });
  },

  /** Full detail for a single registration (university admin only). */
  getRegistration(id: string): Promise<PartnerRegistration> {
    return api.get<PartnerRegistration>(`/admin/partners/${id}`);
  },

  approve(
    id: string,
    body: {
      trust_level: TrustLevel;
      package_id?: string | null;
      note?: string | null;
      version?: number;
    },
  ): Promise<{ organization_id: string; status: string }> {
    return api.post(`/admin/partners/${id}/approve`, body);
  },

  reject(
    id: string,
    body: { reason: string; version?: number },
  ): Promise<{ registration_id?: string; status: string }> {
    return api.post(`/admin/partners/${id}/reject`, body);
  },
};
