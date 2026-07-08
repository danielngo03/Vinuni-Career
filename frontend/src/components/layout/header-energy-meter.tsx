"use client";

import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Lightning } from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { aiAssistantApi } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import { cn } from "@/lib/utils";
import {
  deriveEnergyMeterState,
  headerEnergyMeterVisible,
  type AiEnergyTone,
} from "./ai-energy-meter";

const BILLING_HREF = "/student/billing";

/** Per-tone token classes (v9 Monochrome: green = healthy energy, amber = warn,
 * VinUni red = blocked). The icon + hairline bar fill carry the state color; the
 * % figure stays high contrast so the indicator is never color-only. */
const TONE_STYLES: Record<
  AiEnergyTone,
  { border: string; bg: string; icon: string; text: string; fill: string }
> = {
  ok: {
    border: "border-[var(--border-default)]",
    bg: "bg-[var(--surface-card)] hover:bg-[var(--bg-subtle)]",
    icon: "text-[var(--teal-600)]",
    text: "text-[var(--text-primary)]",
    fill: "bg-[var(--teal-500)]",
  },
  warn: {
    border: "border-[var(--amber-500)]/40",
    bg: "bg-[var(--amber-50)] hover:bg-[var(--amber-100)]",
    icon: "text-[var(--amber-600)]",
    text: "text-[var(--amber-700)]",
    fill: "bg-[var(--amber-500)]",
  },
  block: {
    border: "border-[var(--red-600)]/40",
    bg: "bg-[var(--red-50)] hover:bg-[var(--red-100)]",
    icon: "text-[var(--red-600)]",
    text: "text-[var(--red-600)]",
    fill: "bg-[var(--red-600)]",
  },
};

/**
 * Compact "AI energy" indicator for the student marketplace header quick-actions
 * row — surfacing remaining AI energy at the point of action, next to the
 * notification/messaging/saved/assistant affordances.
 *
 * Reuses the exact same masked energy source as the sidebar usage card
 * (`aiAssistantApi.myUsage()` / `GET /ai/usage/me`, shared React Query key
 * `["ai","usage","me"]` — one fetch, one cache) and the shared
 * `deriveEnergyMeterState` derivation, so header and sidebar never drift. Only
 * the remaining energy **percentage** and block/warn state are shown — never a
 * token/USD/provider/model number.
 *
 * States (v9 Monochrome): OK = green, warn (≥80% used / backend soft-warning) =
 * amber, blocked (weekly energy exhausted) = red. The whole chip links to
 * `/student/billing` so a warned/blocked student can top up or upgrade; the
 * accessible label always carries the numeric percentage (not color-only).
 *
 * Self-guarding: renders only for an authenticated student, and only once the
 * usage payload has loaded (no skeleton flash in the compact header cluster).
 */
export function HeaderEnergyMeter() {
  const t = useTranslations("nav.usage");
  const status = useAuthStore((s) => s.status);
  const persona = useAuthStore((s) => s.user?.persona);
  const visible = headerEnergyMeterVisible(status, persona);

  const usage = useQuery({
    queryKey: ["ai", "usage", "me"],
    queryFn: () => aiAssistantApi.myUsage(),
    enabled: visible,
    staleTime: 60_000,
    refetchInterval: 120_000,
    retry: false,
  });

  const u = usage.data;
  if (!visible || !u) return null;

  const { pct, fillPct, tone } = deriveEnergyMeterState(u);
  const styles = TONE_STYLES[tone];

  const label =
    tone === "block"
      ? t("headerLabelBlocked")
      : tone === "warn"
        ? t("headerLabelLow", { pct })
        : t("headerLabelOk", { pct });

  return (
    <Link
      href={BILLING_HREF}
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex h-9 items-center gap-2 rounded-lg border px-2.5 outline-none transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
        styles.border,
        styles.bg,
      )}
    >
      <Lightning
        aria-hidden
        weight="fill"
        className={cn("size-4 shrink-0", styles.icon)}
      />
      {/* Hairline precise bar — the signature. role=meter carries the numeric
          value so the affordance is never color-only. */}
      <span
        role="meter"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
        className="block h-1 w-7 overflow-hidden rounded-full bg-[var(--bg-muted)]"
      >
        <span
          className={cn(
            "block h-full rounded-full transition-[width] duration-500 motion-reduce:transition-none",
            styles.fill,
          )}
          style={{ width: `${fillPct}%` }}
        />
      </span>
      <span
        aria-hidden
        className={cn(
          "text-[0.8125rem] font-semibold leading-none tabular-nums",
          styles.text,
        )}
      >
        {t("energyPct", { pct })}
      </span>
    </Link>
  );
}
