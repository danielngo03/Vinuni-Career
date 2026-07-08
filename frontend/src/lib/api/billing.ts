import { api, apiFetch } from "./client";
import type { ApiEnvelope } from "./types";

/* ------------------------------- Vocabularies ----------------------------- */

/**
 * Subscription lifecycle (ADR-0010 §2). Manual/bank-transfer payment
 * (`mark_paid`) is the single activation gate — there is no separate approval
 * state. `pending` = chose a paid plan, awaiting the bank-transfer confirm;
 * `active` = admin recorded payment, inside [start_at, end_at]; `expired` /
 * `cancelled` are terminal and revert to the default-plan limits.
 */
export type SubscriptionStatus = "pending" | "active" | "expired" | "cancelled";

/** Who a plan is sold to. A plan is only subscribable by its matching principal. */
export type BillingAudience = "student" | "partner";

export type BillingPeriod = "monthly" | "annual";

export const SUBSCRIPTION_STATUSES: SubscriptionStatus[] = [
  "pending",
  "active",
  "expired",
  "cancelled",
];

/* ------------------------------- Wire types ------------------------------- */

/**
 * The structured grants a tier unlocks (`plan.limits`). Keys vary by audience:
 * students expose `cv_active_quota` / `pdf_exports_per_month` / `premium_templates`
 * / `mass_apply_limit`; partners expose `job_post_quota` / `featured_job_slots` /
 * `passive_search_quota` / `email_blast_quota`. Values are numbers or booleans.
 */
export type PlanLimits = Record<string, number | boolean | string | null>;

/**
 * A pricing tier (`GET /billing/plans`). `price_amount` is a decimal string
 * (e.g. "99000.00", "0.00"); render via `formatVnd`. The default tier
 * (`is_default`) is the free/baseline plan whose limits apply with no row.
 */
export interface SubscriptionPlan {
  id: string;
  code: string;
  /** Locale-resolved display name (server returns vi by default). */
  name: string;
  name_vi: string;
  name_en: string;
  audience: BillingAudience;
  audience_label: string;
  billing_period: BillingPeriod;
  billing_period_label: string;
  duration_days: number;
  price_amount: string | null;
  currency: string;
  limits: PlanLimits;
  is_default: boolean;
  is_visible: boolean;
  sort_order: number;
}

/**
 * A subscription projection. The subscriber surface omits `payment_reference` /
 * `principal_id` / `requested_by` / `paid_by` / `cancel_reason` (admin-only spend
 * oversight); the admin surface (`admin: true`) includes them. `price_amount` is
 * the frozen snapshot taken at request time.
 */
export interface Subscription {
  id: string;
  principal_type: "user" | "org";
  plan_id: string;
  plan: SubscriptionPlan | null;
  billing_period: BillingPeriod;
  billing_period_label: string;
  price_amount: string | null;
  currency: string;
  status: SubscriptionStatus;
  status_label: string;
  start_at: string | null;
  end_at: string | null;
  is_paid: boolean;
  paid_at: string | null;
  requested_at: string | null;
  activated_at: string | null;
  expired_at: string | null;
  cancelled_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  version: number;
  /* Admin-only spend-oversight fields (present on /admin/billing only). */
  principal_id?: string;
  payment_reference?: string | null;
  requested_by?: string;
  paid_by?: string | null;
  cancel_reason?: string | null;
}

/**
 * Static, PII-safe manual/bank-transfer instructions surfaced on a freshly
 * requested (pending) subscription. V1 = manual billing; there is no gateway.
 */
export interface PaymentInstructions {
  method: string;
  bank_name: string;
  account_name: string;
  account_number: string;
  note_hint: string;
}

/** `POST /billing/subscription` result: the new pending sub + how to pay. */
export interface SubscriptionRequestResult extends Subscription {
  payment_instructions: PaymentInstructions;
}

/**
 * `GET /billing/subscription` — the caller's current subscription plus the
 * effective limits. Null-safe: with no in-flight subscription, `subscription` is
 * null and `limits` falls back to the audience's default (free) plan.
 */
export interface MySubscription {
  subscription: Subscription | null;
  audience: BillingAudience;
  limits: PlanLimits;
  default_plan: SubscriptionPlan | null;
}

/** University revenue roll-up returned alongside the admin subscription list. */
export interface BillingRevenue {
  active_revenue_amount: string;
  currency: string;
  active_count: number;
  pending_count: number;
}

export interface AdminPlanCreateBody {
  code: string;
  name: string;
  name_en: string;
  audience: BillingAudience;
  billing_period?: BillingPeriod;
  duration_days?: number;
  price_amount?: number | string;
  currency?: string;
  limits?: PlanLimits;
  is_default?: boolean;
  is_visible?: boolean;
  sort_order?: number;
}

export interface AdminPlanUpdateBody {
  name?: string;
  name_en?: string;
  billing_period?: BillingPeriod;
  duration_days?: number;
  price_amount?: number | string;
  currency?: string;
  limits?: PlanLimits;
  is_default?: boolean;
  is_visible?: boolean;
  sort_order?: number;
}

/* --------------------------------- Calls ---------------------------------- */

export const billingApi = {
  /* ----------------------------- Subscriber ----------------------------- */

  /** Visible plans for an audience (name + price + period + what each grants). */
  listPlans(audience?: BillingAudience): Promise<SubscriptionPlan[]> {
    return api.get<SubscriptionPlan[]>("/billing/plans", {
      query: { audience: audience ?? undefined },
    });
  },

  /** The caller's current subscription + effective limits (null-safe). */
  getMySubscription(): Promise<MySubscription> {
    return api.get<MySubscription>("/billing/subscription");
  },

  /**
   * Request a paid plan → `pending` + bank-transfer `payment_instructions`.
   * 409 (`details.reason === "subscription_exists"`) when one is already
   * in-flight; 422 (`plan_audience_mismatch` / `invalid_plan`) on a bad plan.
   */
  requestSubscription(planId: string): Promise<SubscriptionRequestResult> {
    return api.post<SubscriptionRequestResult>("/billing/subscription", {
      plan_id: planId,
    });
  },

  /**
   * Cancel the caller's own pending/active subscription (reverts to default
   * limits). The self-service endpoint targets the caller's single in-flight
   * row — there is no id in the path. `version` enables optimistic concurrency.
   */
  cancelMySubscription(version?: number): Promise<Subscription> {
    return api.post<Subscription>("/billing/subscription/cancel", { version });
  },

  /* --------------------------- University admin ------------------------- */

  /** All plans, including hidden/admin-only catalogue entries. */
  listAdminPlans(audience?: BillingAudience): Promise<SubscriptionPlan[]> {
    return api.get<SubscriptionPlan[]>("/admin/billing/plans", {
      query: { audience: audience ?? undefined },
    });
  },

  /** Create a plan/quota catalogue entry without a code deploy. */
  createPlan(body: AdminPlanCreateBody): Promise<SubscriptionPlan> {
    return api.post<SubscriptionPlan>("/admin/billing/plans", body);
  },

  /** Patch a plan's names, price, visibility/default flag, or quota limits. */
  updatePlan(
    planId: string,
    body: AdminPlanUpdateBody,
  ): Promise<SubscriptionPlan> {
    return api.patch<SubscriptionPlan>(`/admin/billing/plans/${planId}`, body);
  },

  /**
   * ALL subscriptions + the revenue roll-up (`meta.revenue`). University
   * moderators / superadmin only (permission → 403). Returns the items, the
   * revenue roll-up, and the total count from the envelope meta.
   */
  async listAllSubscriptions(opts?: {
    status?: SubscriptionStatus | null;
    audience?: BillingAudience | null;
    principalId?: string | null;
    limit?: number;
  }): Promise<{ items: Subscription[]; revenue: BillingRevenue | null; count: number }> {
    const res = await apiFetch<ApiEnvelope<Subscription[]>>(
      "/admin/billing/subscriptions",
      {
        method: "GET",
        query: {
          status: opts?.status ?? undefined,
          audience: opts?.audience ?? undefined,
          principal_id: opts?.principalId ?? undefined,
          limit: opts?.limit,
        },
      },
    );
    const meta = (res.meta ?? {}) as {
      revenue?: BillingRevenue;
      count?: number;
    };
    return {
      items: res.data,
      revenue: meta.revenue ?? null,
      count: typeof meta.count === "number" ? meta.count : res.data.length,
    };
  },

  /** Record a manual/bank-transfer payment (sets reference + activates). */
  markPaid(
    subscriptionId: string,
    paymentReference: string,
    version?: number,
  ): Promise<Subscription> {
    return api.post<Subscription>(
      `/admin/billing/subscriptions/${subscriptionId}/mark-paid`,
      { payment_reference: paymentReference, version },
    );
  },

  /** Admin revoke/reject a subscription (reverts to default limits). */
  adminCancelSubscription(
    subscriptionId: string,
    opts?: { reason?: string; version?: number },
  ): Promise<Subscription> {
    return api.post<Subscription>(
      `/admin/billing/subscriptions/${subscriptionId}/cancel`,
      { reason: opts?.reason, version: opts?.version },
    );
  },
};
