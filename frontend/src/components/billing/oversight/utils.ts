import type { BillingAudience, SubscriptionPlan, SubscriptionStatus } from "@/lib/api";

export const AUDIENCE_FILTERS = ["all", "student", "partner"] as const;

export function statusFilters(
  statuses: readonly SubscriptionStatus[],
): readonly (SubscriptionStatus | "all")[] {
  return ["all", ...statuses] as const;
}

export type DialogKind = "markPaid" | "cancel" | null;
export type PlanDialogKind = "create" | "edit" | null;

export type PlanForm = {
  code: string;
  name: string;
  nameEn: string;
  audience: BillingAudience;
  billingPeriod: "monthly" | "annual";
  durationDays: string;
  priceAmount: string;
  currency: string;
  limitsText: string;
  isDefault: boolean;
  isVisible: boolean;
  sortOrder: string;
};

export const EMPTY_PLAN_FORM: PlanForm = {
  code: "",
  name: "",
  nameEn: "",
  audience: "student",
  billingPeriod: "monthly",
  durationDays: "30",
  priceAmount: "0",
  currency: "VND",
  limitsText: "{\n  \"ai_daily_cost_quota_usd\": 0.2\n}",
  isDefault: false,
  isVisible: true,
  sortOrder: "0",
};

export function planFormFrom(plan: SubscriptionPlan): PlanForm {
  return {
    code: plan.code,
    name: plan.name_vi,
    nameEn: plan.name_en,
    audience: plan.audience,
    billingPeriod: plan.billing_period,
    durationDays: String(plan.duration_days),
    priceAmount: plan.price_amount ?? "0",
    currency: plan.currency,
    limitsText: JSON.stringify(plan.limits ?? {}, null, 2),
    isDefault: plan.is_default,
    isVisible: plan.is_visible,
    sortOrder: String(plan.sort_order),
  };
}
