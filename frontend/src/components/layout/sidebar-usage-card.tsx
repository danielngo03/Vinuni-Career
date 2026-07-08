"use client";

import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { aiAssistantApi, billingApi, type AiUsageWindow } from "@/lib/api";
import { useAuthStore, type Persona } from "@/stores/auth-store";
import { cn } from "@/lib/utils";

/**
 * Sidebar footer card: AI request quota meters (real counts from
 * `GET /ai/usage/me` — daily window + weekly window, the same two gates the
 * backend enforces with 409 QUOTA_EXCEEDED) and, for partners, the current
 * subscription plan (`GET /billing/subscription`). Warns at ≥80%, shows the
 * blocked state (week dominates day) with an upgrade link into billing.
 * Hidden while loading, on error, and in the collapsed icon rail.
 */
export function SidebarUsageCard({ persona }: { persona: Persona }) {
  const t = useTranslations("nav.usage");
  const authed = useAuthStore((s) => s.status === "authenticated");

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

  const planName =
    subscription.data?.subscription?.plan?.name ??
    subscription.data?.default_plan?.name ??
    null;
  const billingHref = `/${persona}/billing`;
  const showUpgrade = (u.warning || u.blocked) && persona === "partner";

  return (
    <div className="mx-1 rounded-[10px] border border-[var(--border-default)] bg-[var(--bg-subtle)] p-3">
      <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
        {t("title")}
      </p>

      <UsageMeter
        label={t("dayLabel")}
        window={u.day}
        blocked={u.blocked_scope === "day"}
        countLabel={t("count", { used: u.day.used, limit: u.day.limit })}
      />
      <UsageMeter
        label={t("weekLabel")}
        window={u.week}
        blocked={u.blocked_scope === "week"}
        countLabel={t("count", { used: u.week.used, limit: u.week.limit })}
      />

      {u.blocked ? (
        <p className="mt-2 text-[0.6875rem] font-medium text-[var(--red-600)]">
          {u.blocked_scope === "week" ? t("weekLimitReached") : t("dayLimitReached")}
        </p>
      ) : u.warning ? (
        <p className="mt-2 text-[0.6875rem] font-medium text-[var(--amber-700)]">
          {t("nearLimit")}
        </p>
      ) : null}

      {showUpgrade && (
        <Link
          href={billingHref}
          className="mt-1 inline-flex items-center gap-1 text-[0.6875rem] font-semibold text-[var(--text-primary)] underline underline-offset-2 outline-none hover:text-[var(--text-secondary)] focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
        >
          {t("upgrade")}
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
    </div>
  );
}

function UsageMeter({
  label,
  window: w,
  blocked,
  countLabel,
}: {
  label: string;
  window: AiUsageWindow;
  blocked: boolean;
  countLabel: string;
}) {
  const critical = blocked || w.pct >= 95;
  const warning = !critical && w.pct >= 80;

  return (
    <div className="mt-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[0.6875rem] font-medium text-[var(--text-secondary)]">
          {label}
        </span>
        <span className="text-[0.6875rem] font-semibold tabular-nums text-[var(--text-secondary)]">
          {countLabel}
        </span>
      </div>
      <div
        role="meter"
        aria-valuenow={w.pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
        className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-[var(--bg-muted)]"
      >
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-500 motion-reduce:transition-none",
            critical
              ? "bg-[var(--red-600)]"
              : warning
                ? "bg-[var(--amber-500)]"
                : "bg-[var(--text-primary)]",
          )}
          style={{ width: `${Math.max(w.pct, w.used > 0 ? 4 : 0)}%` }}
        />
      </div>
    </div>
  );
}
