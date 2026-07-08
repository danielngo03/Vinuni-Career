import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "./client";

/* -------------------------------------------------------------------------- */
/* University cross-persona account governance                                 */
/*                                                                             */
/* Backend: `/api/v1/university/governance/accounts` (grant-gated in the        */
/* service layer on `accounts:govern` + acting-university org; superadmin       */
/* bypasses). The university control plane governs BOTH student and             */
/* partner-member accounts. Projections are privacy-safe: no CVs, tokens, raw   */
/* IP/UA, or AI internals ever cross this boundary. Every write records a       */
/* required, audited reason.                                                    */
/* -------------------------------------------------------------------------- */

/** Personas the backend list may return (cross-persona control plane). */
export const GOVERNED_PERSONAS = [
  "student",
  "partner_member",
  "university_staff",
] as const;
export type GovernedPersona = (typeof GOVERNED_PERSONAS)[number];

/** One row from `GET /university/governance/accounts` (offset-paginated). */
export interface GovernedAccountRow {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  /** Superadmin targets are protected: a non-superadmin governor cannot act. */
  is_superadmin: boolean;
  email_verified: boolean;
  /** Primary-identity persona (`student` | `partner_member` | `university_staff`). */
  persona: string;
  org_id: string | null;
  created_at: string | null;
}

/** Offset-pagination envelope for the account list. */
export interface GovernedAccountsPage {
  items: GovernedAccountRow[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/** Query params for the account list. `q` searches email + name. */
export interface GovernedAccountsParams {
  /** `student` | `partner_member` | `university_staff`; omit for all. */
  persona?: string;
  q?: string;
  page?: number;
  page_size?: number;
}

/** One identity attached to an account (from the detail projection). */
export interface GovernedAccountIdentity {
  persona: string;
  org_id: string | null;
  is_primary: boolean;
}

/** Privacy-safe account detail from `GET /university/governance/accounts/{id}`. */
export interface GovernedAccountDetail {
  core: {
    id: string;
    email: string;
    full_name: string;
    is_active: boolean;
    is_superadmin: boolean;
    email_verified: boolean;
    created_at: string | null;
    last_login_at: string | null;
  };
  identities: GovernedAccountIdentity[];
  /** Count only — no device/IP/UA metadata is exposed to a governor. */
  active_session_count: number;
}

/** Result of a suspend/reinstate write. */
export interface AccountActiveResult {
  id: string;
  is_active: boolean;
}

const BASE = "/university/governance/accounts";

export const accountGovernanceApi = {
  /**
   * List student + partner-member (+ staff) accounts the caller may govern.
   * `GET /university/governance/accounts?persona=&q=&page=&page_size=`
   * 403 when the caller lacks `accounts:govern` in a university org.
   */
  list(params: GovernedAccountsParams = {}): Promise<GovernedAccountsPage> {
    const { persona, q, page, page_size } = params;
    return api.get<GovernedAccountsPage>(BASE, {
      query: { persona, q, page, page_size },
    });
  },

  /**
   * Privacy-safe account detail (core + identities + active session count).
   * `GET /university/governance/accounts/{id}`
   * A non-superadmin governor cannot inspect a superadmin account (403).
   */
  detail(id: string): Promise<GovernedAccountDetail> {
    return api.get<GovernedAccountDetail>(`${BASE}/${id}`);
  },

  /**
   * Suspend an account with a required, audited reason (1–500 chars).
   * `POST /university/governance/accounts/{id}/suspend`
   * 422 if the reason is empty/too long; 403 for a protected/self target.
   */
  suspend(id: string, reason: string): Promise<AccountActiveResult> {
    return api.post<AccountActiveResult>(`${BASE}/${id}/suspend`, { reason });
  },

  /**
   * Reinstate a suspended account with a required, audited reason (1–500 chars).
   * `POST /university/governance/accounts/{id}/reinstate`
   */
  reinstate(id: string, reason: string): Promise<AccountActiveResult> {
    return api.post<AccountActiveResult>(`${BASE}/${id}/reinstate`, { reason });
  },
};

/* -------------------------------------------------------------------------- */
/* React Query hooks                                                            */
/* -------------------------------------------------------------------------- */

export const accountGovernanceKeys = {
  all: ["account-governance"] as const,
  list: (params: GovernedAccountsParams) =>
    ["account-governance", "list", params] as const,
  detail: (id: string) => ["account-governance", "detail", id] as const,
};

/**
 * Paginated account list. `retry: false` so a 403 surfaces immediately as a
 * permission state; `keepPreviousData` avoids a full skeleton flash on page or
 * filter changes.
 */
export function useGovernedAccounts(params: GovernedAccountsParams) {
  return useQuery({
    queryKey: accountGovernanceKeys.list(params),
    queryFn: () => accountGovernanceApi.list(params),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
    retry: false,
  });
}

/** Account detail — only fetched while a target id is set (drawer open). */
export function useGovernedAccountDetail(id: string | null) {
  return useQuery({
    queryKey: accountGovernanceKeys.detail(id ?? "none"),
    queryFn: () => accountGovernanceApi.detail(id as string),
    enabled: id != null,
    retry: false,
  });
}

/** Suspend mutation. Invalidates the list + detail on success. */
export function useSuspendAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: string; reason: string }) =>
      accountGovernanceApi.suspend(vars.id, vars.reason),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: accountGovernanceKeys.all }),
  });
}

/** Reinstate mutation. Invalidates the list + detail on success. */
export function useReinstateAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: string; reason: string }) =>
      accountGovernanceApi.reinstate(vars.id, vars.reason),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: accountGovernanceKeys.all }),
  });
}
