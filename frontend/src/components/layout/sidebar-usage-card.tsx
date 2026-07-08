"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, Infinity as InfinityIcon } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { aiAssistantApi, billingApi } from "@/lib/api";
import { useAuthStore, type Persona } from "@/stores/auth-store";
import { cn } from "@/lib/utils";
import { CapacityRequestDialog } from "@/components/ai-governance/capacity-request-dialog";

/**
 * Sidebar footer card: the caller's AI energy meter (`GET /ai/usage/me`) and,
 * for partners, the current subscription plan (`GET /billing/subscription`).
 *
 * AI usage is a cost-weighted "energy" budget (owner-locked 2026-07-08): the
 * headline is the share of this week's energy that is still REMAINING, shown as
 * a single slim bar (ink normally, amber on warning, red when blocked). A
 * secondary line shows weekly credits used vs the allowance (plus any top-up
 * reserve). Energy is opaque — no tokens, cost, provider, or model ever appear.
 *
 * The exhaustion CTA is persona-aware, driven by the snapshot's `action`:
 *   - `unlimited` (superadmin): a clean "Unlimited" state, no bar, no CTA.
 *   - `request_capacity` (university): opens a capacity-request dialog — energy
 *     is DISTRIBUTED by an admin, never bought.
 *   - `upgrade` (partner): a plan/top-up link into billing.
 *
 * For a shared partner-org pool (`scope === "org"`) the copy uses org framing.
 * Hidden while loading, on error, and in the collapsed icon rail.
 */
export function SidebarUsageCard({ persona }: { persona: Persona }) {
  const t = useTranslations("nav.usage");
  const authed = useAuthStore((s) => s.status === "authenticated");
  const [capacityOpen, setCapacityOpen] = useState(false);

  const usage = useQuery({
    queryKey: ["ai", "usage", "me"],
    queryFn: () => aiAssistantApi.myUsage(),
    enabled: authed,
    staleTime: 60_000,
    refetchInterval: 120_000,
    retry: false,
  });

  const subscription = useQuery({
    queryKey: ["billing", "subscription", "sidebar"],
    queryFn: () => billingApi.getMySubscription(),
    enabled: authed && persona === "partner",
    staleTime: 5 * 60_000,
    retry: false,
  });

  const u = usage.data;
  if (!u) return null;

  // Superadmin / uncapped: a calm, bar-less "Unlimited" state — no CTA.
  if (u.unlimited) {
    return (
      <div className="mx-1 rounded-[10px] border border-[var(--border-default)] bg-[var(--bg-subtle)] p-3">
        <div className="flex items-center justify-between gap-2">
          <p className="min-w-0 truncate text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
            {t("unlimitedTitle")}
          </p>
          <span className="inline-flex shrink-0 items-center gap-1 text-[0.6875rem] font-semibold text-[var(--text-secondary)]">
            <InfinityIcon aria-hidden strokeWidth={2.25} className="size-3.5" />
            {t("unlimitedLabel")}
          </span>
        </div>
        <p className="mt-1.5 text-[0.6875rem] text-[var(--text-muted)]">
          {t("unlimitedHint")}
        </p>
      </div>
    );
  }

  const planName =
    subscription.data?.subscription?.plan?.name ??
    subscription.data?.default_plan?.name ??
    null;
  const billingHref = `/${persona}/billing`;
  const isOrg = u.scope === "org";
  const pct = Math.round(u.energy_pct);

  const isUniversityAction = u.action === "request_capacity";
  const isUpgradeAction = u.action === "upgrade";
  const showUpgrade = (u.warning || u.blocked) && isUpgradeAction && persona === "partner";
  const showRequestCapacity = (u.warning || u.blocked) && isUniversityAction;

  const blockedCopy =
    u.blocked_reason === "AI_ORG_WEEKLY_ENERGY_EXCEEDED"
      ? t("blockedOrgWeekly")
      : u.blocked_reason === "AI_UNIVERSITY_ALLOCATION_EXCEEDED" ||
          u.blocked_reason === "AI_MEMBER_ALLOCATION_EXCEEDED"
        ? t("blockedUniversity")
        : t("blockedWeekly");

  return (
    <div className="mx-1 rounded-[10px] border border-[var(--border-default)] bg-[var(--bg-subtle)] p-3">
      <div className="flex items-baseline justify-between gap-2">
        <p className="min-w-0 truncate text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
          {isOrg ? t("orgPoolLabel") : t("energyTitle")}
        </p>
        <span
          className={cn(
            "shrink-0 text-[0.6875rem] font-semibold tabular-nums",
            u.blocked
              ? "text-[var(--red-600)]"
              : u.warning
                ? "text-[var(--amber-700)]"
                : "text-[var(--text-secondary)]",
          )}
        >
          {t("energyRemaining", { pct })}
        </span>
      </div>

      <div
        role="meter"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={isOrg ? t("orgPoolLabel") : t("energyTitle")}
        className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-[var(--bg-muted)]"
      >
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-500 motion-reduce:transition-none",
            u.blocked
              ? "bg-[var(--red-600)]"
              : u.warning
                ? "bg-[var(--amber-500)]"
                : "bg-[var(--text-primary)]",
          )}
          style={{ width: `${Math.min(100, Math.max(0, u.energy_pct))}%` }}
        />
      </div>

      <p className="mt-1.5 text-[0.6875rem] tabular-nums text-[var(--text-secondary)]">
        {t("weeklyLabel", {
          used: u.weekly.used,
          allowance: u.weekly.allowance,
        })}
        {u.weekly.wallet > 0 && (
          <span className="text-[var(--text-muted)]">
            {" "}
            {t("walletLabel", { wallet: u.weekly.wallet })}
          </span>
        )}
      </p>

      {u.session_3h.over_soft_cap && !u.blocked && (
        <p className="mt-1 text-[0.6875rem] font-medium text-[var(--amber-700)]">
          {t("burstHint")}
        </p>
      )}

      {u.blocked ? (
        <p className="mt-2 text-[0.6875rem] font-medium text-[var(--red-600)]">
          {blockedCopy}
        </p>
      ) : u.warning ? (
        <p className="mt-2 text-[0.6875rem] font-medium text-[var(--amber-700)]">
          {t("nearLimit")}
        </p>
      ) : null}

      {/* University: request more capacity (distribution, not billing). */}
      {showRequestCapacity && (
        <button
          type="button"
          onClick={() => setCapacityOpen(true)}
          className="mt-1.5 inline-flex items-center gap-1 text-[0.6875rem] font-semibold text-[var(--text-primary)] underline underline-offset-2 outline-none hover:text-[var(--text-secondary)] focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
        >
          {t("requestCapacity")}
          <ArrowUpRight aria-hidden strokeWidth={2} className="size-3" />
        </button>
      )}

      {/* Partner: plan/top-up upgrade. */}
      {showUpgrade && (
        <Link
          href={billingHref}
          className="mt-1 inline-flex items-center gap-1 text-[0.6875rem] font-semibold text-[var(--text-primary)] underline underline-offset-2 outline-none hover:text-[var(--text-secondary)] focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
        >
          {u.blocked ? t("topUp") : t("upgrade")}
          <ArrowUpRight aria-hidden strokeWidth={2} className="size-3" />
        </Link>
      )}

      {/* Current plan (partner only — real subscription data) */}
      {planName && (
        <div className="mt-2.5 flex items-center justify-between gap-2 border-t border-[var(--border-default)] pt-2.5">
          <span className="min-w-0 truncate text-[0.6875rem] font-medium text-[var(--text-secondary)]">
            {t("plan", { name: planName })}
          </span>
          <Link
            href={billingHref}
            className="shrink-0 text-[0.6875rem] font-semibold text-[var(--text-primary)] underline underline-offset-2 outline-none hover:text-[var(--text-secondary)] focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
          >
            {t("planManage")}
          </Link>
        </div>
      )}

      {isUniversityAction && (
        <CapacityRequestDialog
          open={capacityOpen}
          onClose={() => setCapacityOpen(false)}
        />
      )}
    </div>
  );
}
