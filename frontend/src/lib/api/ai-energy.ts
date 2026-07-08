import { api } from "./client";
import type { AiEnergyUsage } from "./ai-assistant";

/**
 * AI energy WRITE path (partner AI overhaul). Two surfaces:
 *
 *  - Admin (`/organizations/ai-energy`, `billing:manage` gated): the org pool
 *    snapshot + per-department/member allocations, set/clear a weekly sub-cap,
 *    grant a goodwill wallet, and list/confirm bank-transfer top-ups. Confirming
 *    a payment is FINANCE authority (superadmin / VinUni), never a partner admin.
 *  - Member self-service (`/ai/energy`): request a top-up (→ pending + bank
 *    instructions) and list my own top-ups.
 *
 * Energy is an abstract, opaque credit — this layer never carries tokens, USD,
 * provider, model, latency, or prompt data. `price_amount` / `currency` on a
 * top-up (and on a pack) ARE a real product price (VND), like a subscription.
 */

/* ------------------------------- Wire types ------------------------------- */

/** Scope a sub-allocation targets. Departments are advisory, members metered. */
export type AiEnergyAllocationScope = "department" | "user";

/** Scope a top-up / wallet grant can target. Org-scope grants are finance-only. */
export type AiEnergyTopupScope = "user" | "department" | "org";

/** A purchasable top-up pack. `price_amount` is a VND decimal string (real price). */
export interface AiEnergyPack {
  code: string;
  units: number;
  price_amount: string;
  currency: string;
}

/**
 * A member's personal sub-allocation sub-block on the org pool snapshot, present
 * only when an admin has set a per-member weekly sub-cap. All values are opaque
 * energy credits.
 */
export interface AiEnergyAllocationSnapshot {
  allowance: number;
  wallet: number;
  capacity: number;
  used: number;
  energy_pct: number;
  blocked: boolean;
}

/**
 * The organization energy pool (`overview.org_pool`). Same shape as the personal
 * energy meter (`AiEnergyUsage`) plus an optional per-scope `allocation` block.
 * Opaque credits only — never tokens/USD/provider/model.
 */
export interface OrgEnergyPool extends AiEnergyUsage {
  allocation?: AiEnergyAllocationSnapshot | null;
}

/** One department/member sub-allocation row from the admin overview. */
export interface AiEnergyAllocation {
  scope_type: AiEnergyAllocationScope;
  scope_id: string;
  /** null = no sub-cap → the scope shares the org pool. */
  weekly_allowance_units: number | null;
  wallet_units: number;
  weekly_used: number;
  /** Metered/enforced (members) vs advisory-only (departments). */
  enforced: boolean;
}

/** `GET /organizations/ai-energy/overview` — org pool + allocations + packs. */
export interface AiEnergyOverview {
  org_pool: OrgEnergyPool;
  allocations: AiEnergyAllocation[];
  packs: AiEnergyPack[];
}

/** Top-up lifecycle: requested (pending) → finance confirms (paid) | cancelled. */
export type AiEnergyTopupStatus = "pending" | "paid" | "cancelled";

/** A bank-transfer top-up request/record. `price_amount` is a VND decimal string. */
export interface AiEnergyTopup {
  id: string;
  org_id: string | null;
  scope_type: string;
  scope_id: string;
  units: number;
  price_amount: string;
  currency: string;
  status: AiEnergyTopupStatus;
  status_label: string;
  pack_code: string | null;
  payment_reference: string | null;
  requested_by: string;
  paid_at: string | null;
  created_at: string | null;
  version: number;
}

/** Static manual/bank-transfer instructions returned on a freshly requested top-up. */
export interface AiEnergyPaymentInstructions {
  method: string;
  bank_name: string;
  account_name: string;
  account_number: string;
  note_hint: string;
  /** The exact transfer note the member should use, e.g. "VINUNI-ENERGY-AB12CD34". */
  reference_hint: string;
}

/** `POST /ai/energy/topup` result — the new pending top-up + how to pay. */
export interface AiEnergyTopupResult extends AiEnergyTopup {
  payment_instructions: AiEnergyPaymentInstructions;
}

/** `PUT /organizations/ai-energy/allocations` result. */
export interface AiEnergyAllocationResult {
  scope_type: AiEnergyAllocationScope;
  scope_id: string;
  weekly_allowance_units: number | null;
  wallet_units: number;
}

/** `POST /organizations/ai-energy/wallet-grants` result. */
export interface AiEnergyWalletGrantResult {
  scope_type: string;
  scope_id: string;
  wallet_units: number;
}

/* --------------------------------- Calls ---------------------------------- */

export const aiEnergyApi = {
  /* ------------------------------- Admin ------------------------------- */

  /** Org pool snapshot + every department/member allocation + top-up packs. */
  getOverview(): Promise<AiEnergyOverview> {
    return api.get<AiEnergyOverview>("/organizations/ai-energy/overview");
  },

  /**
   * Set (or clear, with `weekly_allowance_units: null`) a department/member
   * weekly sub-cap. `null` returns the scope to sharing the org pool.
   */
  setAllocation(body: {
    scope_type: AiEnergyAllocationScope;
    scope_id: string;
    weekly_allowance_units: number | null;
  }): Promise<AiEnergyAllocationResult> {
    return api.put<AiEnergyAllocationResult>(
      "/organizations/ai-energy/allocations",
      body,
    );
  },

  /** Grant goodwill reserve wallet to a department/member (not a purchase). */
  grantWallet(body: {
    scope_type: AiEnergyAllocationScope;
    scope_id: string;
    units: number;
    reason: string;
  }): Promise<AiEnergyWalletGrantResult> {
    return api.post<AiEnergyWalletGrantResult>(
      "/organizations/ai-energy/wallet-grants",
      body,
    );
  },

  /** All of the caller org's top-ups (management-gated). */
  listOrgTopups(opts?: {
    status?: AiEnergyTopupStatus | null;
    limit?: number;
  }): Promise<AiEnergyTopup[]> {
    return api.get<AiEnergyTopup[]>("/organizations/ai-energy/topups", {
      query: { status: opts?.status ?? undefined, limit: opts?.limit },
    });
  },

  /**
   * Confirm a bank-transfer top-up (credits the scope wallet). FINANCE authority
   * only — a partner admin gets 403; surface that as a permission state.
   */
  confirmTopup(
    topupId: string,
    paymentReference: string,
  ): Promise<AiEnergyTopup> {
    return api.post<AiEnergyTopup>(
      `/organizations/ai-energy/topups/${topupId}/confirm`,
      { payment_reference: paymentReference },
    );
  },

  /* --------------------------- Member self-service --------------------- */

  /**
   * Request a top-up → `pending` + bank-transfer instructions. Defaults to the
   * caller's own (`user`) scope; requesting for a member/department/org requires
   * management.
   */
  requestTopup(body: {
    pack_code: string;
    scope_type?: AiEnergyTopupScope;
    scope_id?: string | null;
  }): Promise<AiEnergyTopupResult> {
    return api.post<AiEnergyTopupResult>("/ai/energy/topup", body);
  },

  /** The caller's own top-ups. */
  listMyTopups(opts?: { limit?: number }): Promise<AiEnergyTopup[]> {
    return api.get<AiEnergyTopup[]>("/ai/energy/topups", {
      query: { limit: opts?.limit },
    });
  },
};
