"use client";

import { useTranslations } from "next-intl";
import {
  CalendarCheck,
  CheckCircle,
  Handshake,
  HourglassMedium,
  Info,
} from "@phosphor-icons/react";
import type { ApplicationNextAction } from "@/lib/api";

type BannerTone = "info" | "attention" | "success" | "muted";

const TONE_ICON: Record<BannerTone, typeof Info> = {
  info: HourglassMedium,
  attention: Handshake,
  success: CheckCircle,
  muted: Info,
};

const TONE_ICON_CHIP: Record<BannerTone, string> = {
  info: "icon-chip-info",
  attention: "icon-chip-warning",
  success: "icon-chip-success",
  muted: "icon-chip-neutral",
};

const TONE_PANEL: Record<BannerTone, string> = {
  info: "border-[var(--border-default)] bg-[var(--glass-surface)]",
  attention: "border-[var(--amber-600)]/40 bg-[var(--amber-100)]",
  // v9 Monochrome: teal is the "verified/success" green hue.
  success: "border-[var(--teal-600)]/40 bg-[var(--teal-100)]",
  muted: "border-[var(--border-default)] bg-[var(--bg-muted)]",
};

/**
 * next_action -> {i18n key stem, tone}. Terminal no-action states stay
 * low-key (muted, no celebratory chrome) EXCEPT `no_action_hired`, which is a
 * genuine verified/success outcome (v9 Monochrome: green = verified/success).
 */
const ACTION_CONFIG: Record<string, { key: string; tone: BannerTone; icon?: typeof Info }> = {
  await_review: { key: "nextActionAwaitReview", tone: "info" },
  in_progress: { key: "nextActionInProgress", tone: "info" },
  prepare_for_interview: {
    key: "nextActionPrepareForInterview",
    tone: "attention",
    icon: CalendarCheck,
  },
  respond_to_offer: {
    key: "nextActionRespondToOffer",
    tone: "attention",
    icon: Handshake,
  },
  no_action_withdrawn: { key: "nextActionNoActionWithdrawn", tone: "muted" },
  no_action_rejected: { key: "nextActionNoActionRejected", tone: "muted" },
  no_action_hired: {
    key: "nextActionNoActionHired",
    tone: "success",
    icon: CheckCircle,
  },
};

/**
 * Honest, non-hype "what happens next" callout driven by the server's
 * `next_action` key. Renders nothing for an unrecognized/absent value rather
 * than guessing.
 */
export function NextActionBanner({
  nextAction,
}: {
  nextAction: ApplicationNextAction | null | undefined;
}) {
  const t = useTranslations("applications");
  if (!nextAction) return null;
  const config = ACTION_CONFIG[nextAction];
  if (!config) return null;

  const Icon = config.icon ?? TONE_ICON[config.tone];

  return (
    <div
      role="status"
      className={`mb-6 flex items-start gap-3 rounded-2xl border p-4 backdrop-blur-md ${TONE_PANEL[config.tone]}`}
    >
      <span
        className={`flex size-8 shrink-0 items-center justify-center rounded-lg shadow-sm ${TONE_ICON_CHIP[config.tone]}`}
      >
        <Icon aria-hidden weight="duotone" className="size-4 text-white" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-[var(--text-primary)]">
          {t(`${config.key}Title`)}
        </p>
        <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
          {t(`${config.key}Body`)}
        </p>
      </div>
    </div>
  );
}
