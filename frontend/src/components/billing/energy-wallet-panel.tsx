"use client";

import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Lightning,
  ArrowUp,
  WarningCircle,
  CheckCircle,
  Wallet,
} from "@phosphor-icons/react";
import { Button, Skeleton } from "@/components/ui";
import { aiAssistantApi } from "@/lib/api";
import { energyWalletView } from "@/lib/billing/energy-wallet";
import { cn } from "@/lib/utils";

/** Anchor id on the plan-comparison section (upgrade nudge scroll target). */
export const BILLING_PLANS_ANCHOR = "billing-plans";

/**
 * Student "AI energy wallet" panel for `/student/billing`. A masked, actionable
 * summary that sits above the detailed usage breakdown: remaining weekly energy
 * %, ok/warn/block state, a coarse top-up-reserve bucket, and a "need more
 * energy?" upgrade nudge that scrolls to the plan comparison.
 *
 * Masking is strict (AI_PRODUCT_SPEC §15): only a percentage, a coarse wallet
 * bucket, and ok/warn/block state are shown — never a raw credit/token/USD
 * figure or any provider/model signal. Reuses the exact same `GET /ai/usage/me`
 * source + shared query key as the header/sidebar meter (one fetch, one cache).
 *
 * Top-up is manual/bank-transfer: V1 has no self-serve top-up endpoint, so the
 * honest path is a plan upgrade (which already creates a pending, manually
 * confirmed bank-transfer request on this same screen) — the nudge routes there.
 */
export function EnergyWalletPanel() {
  const t = useTranslations("billing.energyWallet");
  const locale = useLocale();

  const q = useQuery({
    queryKey: ["ai", "usage", "me"],
    queryFn: () => aiAssistantApi.myUsage(),
    staleTime: 60_000,
    retry: false,
  });

  const heading = (
    <div className="mb-2.5 flex items-center gap-2">
      <span className="flex size-7 items-center justify-center rounded-lg icon-chip-success shadow-sm">
        <Lightning aria-hidden weight="duotone" className="size-4 text-white" />
      </span>
      <div>
        <h2 className="text-sm font-bold text-[var(--text-primary)]">{t("title")}</h2>
        <p className="text-xs text-[var(--text-secondary)]">{t("subtitle")}</p>
      </div>
    </div>
  );

  return (
    <section aria-label={t("title")}>
      {heading}

      {q.isPending ? (
        <div className="space-y-3 rounded-2xl border border-[var(--border-default)] bg-white p-4 shadow-[0_2px_16px_rgba(11,34,57,0.06)]">
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-2 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : q.isError || !q.data ? (
        <div className="flex flex-col items-start gap-2 rounded-2xl border border-[var(--border-default)] bg-white p-4 shadow-[0_2px_16px_rgba(11,34,57,0.06)]">
          <p className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
            <WarningCircle aria-hidden weight="duotone" className="size-5 text-[var(--brand-red)]" />
            {t("errorTitle")}
          </p>
          <p className="text-sm text-[var(--text-secondary)]">{t("errorBody")}</p>
          <Button variant="secondary" size="sm" onClick={() => q.refetch()}>
            {t("retry")}
          </Button>
        </div>
      ) : (
        <WalletBody data={q.data} locale={locale} t={t} />
      )}
    </section>
  );
}

function WalletBody({
  data,
  locale,
  t,
}: {
  data: Parameters<typeof energyWalletView>[0];
  locale: string;
  t: ReturnType<typeof useTranslations<"billing.energyWallet">>;
}) {
  const view = energyWalletView(data);
  const weekReset = relativeReset(data.week_reset, locale);

  const noteTone = view.blocked ? "block" : view.tone === "warn" ? "warn" : "ok";
  const noteText = view.blocked
    ? t("blockedNote")
    : view.tone === "warn"
      ? t("warnNote")
      : t("okNote");

  return (
    <div className="space-y-4 rounded-2xl border border-[var(--border-default)] bg-white p-4 shadow-[0_2px_16px_rgba(11,34,57,0.06)]">
      {/* Masked meter */}
      <div>
        <div className="flex items-end justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs font-medium text-[var(--text-secondary)]">
              {view.isOrg ? t("orgPoolLabel") : t("meterLabel")}
            </p>
            <p
              className={cn(
                "text-2xl font-bold tabular-nums leading-tight",
                view.blocked ? "text-[var(--red-600)]" : "text-[var(--text-primary)]",
              )}
            >
              {t("remaining", { pct: view.pct })}
            </p>
          </div>
          {/* Coarse top-up reserve bucket — never a raw credit count. */}
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold",
              view.walletBucket === "reserve"
                ? "border-[var(--teal-100)] bg-[var(--teal-50)] text-[var(--teal-700)]"
                : "border-[var(--border-default)] bg-[var(--surface-secondary)] text-[var(--text-muted)]",
            )}
          >
            <Wallet aria-hidden weight="duotone" className="size-3.5" />
            {view.walletBucket === "reserve" ? t("walletReserve") : t("walletNone")}
          </span>
        </div>

        <div
          role="meter"
          aria-valuenow={view.pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={view.isOrg ? t("orgPoolLabel") : t("meterLabel")}
          className="mt-2 h-2 w-full overflow-hidden rounded-full bg-[var(--bg-muted)]"
        >
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-500 motion-reduce:transition-none",
              view.blocked
                ? "bg-[var(--red-600)]"
                : view.tone === "warn"
                  ? "bg-[var(--amber-500)]"
                  : "bg-[var(--text-primary)]",
            )}
            style={{ width: `${view.fillPct}%` }}
          />
        </div>

        {weekReset && (
          <p className="mt-1.5 text-xs text-[var(--text-muted)]">
            {t("resetsIn", { when: weekReset })}
          </p>
        )}
      </div>

      {/* State note */}
      <p
        className={cn(
          "flex items-start gap-2 rounded-lg border px-3 py-2 text-xs font-medium",
          noteTone === "block"
            ? "border-[var(--red-400)] bg-[var(--red-50)] text-[var(--red-700)]"
            : noteTone === "warn"
              ? "border-[var(--amber-400)] bg-[var(--amber-50)] text-[var(--amber-700)]"
              : "border-[var(--teal-100)] bg-[var(--teal-50)] text-[var(--teal-700)]",
        )}
      >
        {noteTone === "ok" ? (
          <CheckCircle aria-hidden weight="fill" className="mt-0.5 size-3.5 shrink-0" />
        ) : (
          <WarningCircle aria-hidden weight="fill" className="mt-0.5 size-3.5 shrink-0" />
        )}
        {noteText}
      </p>

      {/* Top-up / upgrade nudge */}
      <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-subtle)] p-3.5">
        <p className="text-sm font-semibold text-[var(--text-primary)]">{t("needMoreTitle")}</p>
        <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">
          {t("needMoreBody")}
        </p>
        <a
          href={`#${BILLING_PLANS_ANCHOR}`}
          className="mt-2.5 inline-flex items-center gap-1.5 rounded-lg bg-[var(--brand-primary)] px-3.5 py-2 text-sm font-semibold text-[var(--text-inverted)] outline-none transition-opacity hover:opacity-90 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
        >
          <ArrowUp aria-hidden weight="bold" className="size-4" />
          {t("upgrade")}
        </a>
      </div>
    </div>
  );
}

/** Localized "in Xh" for the (future) weekly reset instant. Client-only. */
function relativeReset(iso: string | null | undefined, locale: string): string | null {
  if (!iso) return null;
  const target = new Date(iso).getTime();
  if (Number.isNaN(target)) return null;
  const diffMs = target - Date.now();
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const absMin = Math.abs(diffMs) / 60_000;
  if (absMin < 60) return rtf.format(Math.max(1, Math.round(diffMs / 60_000)), "minute");
  if (absMin < 60 * 24) return rtf.format(Math.round(diffMs / 3_600_000), "hour");
  return rtf.format(Math.round(diffMs / 86_400_000), "day");
}
