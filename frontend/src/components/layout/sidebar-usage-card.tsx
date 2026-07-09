"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight } from "lucide-react";
import { Link } from "@/i18n/navigation";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { aiAssistantApi, billingApi, type AiUsageWindow } from "@/lib/api";
import { useAuthStore, type Persona } from "@/stores/auth-store";
import { cn } from "@/lib/utils";

type UsageT = ReturnType<typeof useTranslations<"nav.usage">>;

/**
 * Sidebar footer card: AI request quota meters (real counts from
 * `GET /ai/usage/me` — rolling 3h session + weekly request windows) rendered as
 * PERCENT USED, and, for partners, the current subscription plan
 * (`GET /billing/subscription`). Each meter's bar reveals a live "time until
 * reset" tooltip (computed client-side from the window's `resets_at`). Warns at
 * ≥80%, shows the blocked state with an upgrade link into billing.
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
    <TooltipProvider delayDuration={150}>
      <div className="mx-1 rounded-[10px] border border-[var(--border-default)] bg-[var(--bg-subtle)] p-3">
        <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
          {t("title")}
        </p>

        <UsageMeter
          label={t("sessionLabel")}
          window={u.session}
          blocked={u.blocked_scope === "session"}
          idleFallback={t("sessionIdle")}
          t={t}
        />
        <UsageMeter
          label={t("weekLabel")}
          window={u.week}
          blocked={u.blocked_scope === "week"}
          idleFallback={null}
          t={t}
        />

        {u.blocked ? (
          <p className="mt-2 text-[0.6875rem] font-medium text-[var(--red-600)]">
            {u.blocked_scope === "week" ? t("weekLimitReached") : t("sessionLimitReached")}
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
    </TooltipProvider>
  );
}

function UsageMeter({
  label,
  window: w,
  blocked,
  idleFallback,
  t,
}: {
  label: string;
  window: AiUsageWindow;
  blocked: boolean;
  /** Tooltip text when the (rolling) window has nothing pending to reset. */
  idleFallback: string | null;
  t: UsageT;
}) {
  const [open, setOpen] = useState(false);
  const critical = blocked || w.pct >= 95;
  const warning = !critical && w.pct >= 80;

  // Recomputed on each open (controlled state forces a fresh render), so the
  // countdown reflects the current wall clock at hover/focus time.
  const resetText = formatReset(w.resets_at, t) ?? idleFallback;
  const usedText = t("pctUsed", { pct: w.pct });
  const ariaLabel = resetText ? `${label}: ${usedText}. ${resetText}` : `${label}: ${usedText}`;

  return (
    <div className="mt-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[0.6875rem] font-medium text-[var(--text-secondary)]">
          {label}
        </span>
        <span className="text-[0.6875rem] font-semibold tabular-nums text-[var(--text-secondary)]">
          {w.pct}%
        </span>
      </div>
      <Tooltip open={open} onOpenChange={setOpen}>
        <TooltipTrigger asChild>
          <span
            role="meter"
            tabIndex={0}
            aria-valuenow={w.pct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={ariaLabel}
            className="mt-1 block h-1.5 w-full cursor-default overflow-hidden rounded-full bg-[var(--bg-muted)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
          >
            <span
              aria-hidden
              className={cn(
                "block h-full rounded-full transition-[width] duration-500 motion-reduce:transition-none",
                critical
                  ? "bg-[var(--red-600)]"
                  : warning
                    ? "bg-[var(--amber-500)]"
                    : "bg-[var(--text-primary)]",
              )}
              style={{ width: `${Math.max(w.pct, w.used > 0 ? 4 : 0)}%` }}
            />
          </span>
        </TooltipTrigger>
        {resetText && (
          <TooltipContent side="top" className="max-w-[14rem]">
            {resetText}
          </TooltipContent>
        )}
      </Tooltip>
    </div>
  );
}

/**
 * Client-side "time until reset" from an ISO-8601 instant, e.g. "Còn 2 giờ 14
 * phút nữa reset" / "Resets in 2h 14m". Shows the two most-significant non-zero
 * units (day/hour/minute), collapses to "resetting soon" under a minute, and
 * returns `null` when there is no pending reset instant.
 */
function formatReset(resetsAt: string | null, t: UsageT): string | null {
  if (!resetsAt) return null;
  const target = new Date(resetsAt).getTime();
  if (Number.isNaN(target)) return null;

  const diffMs = target - Date.now();
  if (diffMs <= 60_000) return t("resetsSoon");

  const totalMin = Math.floor(diffMs / 60_000);
  const days = Math.floor(totalMin / 1440);
  const hours = Math.floor((totalMin % 1440) / 60);
  const minutes = totalMin % 60;

  const parts: string[] = [];
  if (days > 0) parts.push(t("unitDay", { n: days }));
  if (hours > 0) parts.push(t("unitHour", { n: hours }));
  // Minutes only when the horizon is under a day, so the week meter reads
  // "3 ngày 5 giờ" rather than a noisy "3 ngày 5 giờ 12 phút".
  if (minutes > 0 && days === 0) parts.push(t("unitMinute", { n: minutes }));

  const shown = parts.slice(0, 2);
  if (shown.length === 0) return t("resetsSoon");
  return t("resetsIn", { parts: shown.join(" ") });
}
