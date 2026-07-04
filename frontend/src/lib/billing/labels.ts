"use client";

import { useTranslations } from "next-intl";
import type {
  PlanLimits,
  SubscriptionStatus,
} from "@/lib/api";
import type { StatusTone } from "@/components/ui";

/**
 * Localized enum labels for subscriptions. The backend pairs every code with a
 * vi `*_label` (it presents in vi by default); for vi/en parity we map the stable
 * CODE through next-intl and fall back to the server label, then the raw code.
 * Raw enum codes are never shown to the user.
 */
export function useBillingLabels() {
  const t = useTranslations("billing.enums");

  const make =
    (group: string) =>
    (code: string | null | undefined, serverLabel?: string | null): string => {
      if (!code) return serverLabel || "—";
      const key = `${group}.${code}`;
      if (t.has(key)) return t(key);
      return serverLabel || code;
    };

  return {
    status: make("status"),
    audience: make("audience"),
    period: make("period"),
  };
}

/** Subscription status → StatusBadge tone (color is never the only signal). */
export const SUBSCRIPTION_STATUS_TONE: Record<SubscriptionStatus, StatusTone> = {
  pending: "pending",
  active: "active",
  expired: "closed",
  cancelled: "rejected",
};

/**
 * Localized labels for the structured grant keys plus a humanized display value.
 * Unknown keys fall back to a title-cased version of the key; booleans render as
 * a check/dash, numbers render verbatim. Returns ordered rows so the comparison
 * tables list grants consistently.
 */
export function useLimitLabels() {
  const t = useTranslations("billing.limits");

  function labelFor(key: string): string {
    if (t.has(`keys.${key}`)) return t(`keys.${key}`);
    return key
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function displayValue(value: number | boolean | string | null): string {
    if (typeof value === "boolean") {
      return value ? t("on") : t("off");
    }
    if (value === null || value === undefined) return "—";
    return String(value);
  }

  /** Stable, ordered (key,label,display) rows for a limits map. */
  function rows(
    limits: PlanLimits,
  ): { key: string; label: string; value: number | boolean | string | null; display: string }[] {
    return Object.entries(limits).map(([key, value]) => ({
      key,
      label: labelFor(key),
      value,
      display: displayValue(value),
    }));
  }

  return { labelFor, displayValue, rows };
}
