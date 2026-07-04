"use client";

import { useTranslations } from "next-intl";
import type { StatusTone } from "@/components/ui";
import type { ApplicationStatus, RevealStatus } from "@/lib/api";

/**
 * Map an application status to a StatusBadge tone. Color is always paired with
 * a text label (the badge children), never the sole signal.
 */
export const APPLICATION_STATUS_TONE: Record<string, StatusTone> = {
  submitted: "info",
  under_review: "pending",
  rejected: "rejected",
  withdrawn: "closed",
  // ADR-0007 terminal positive outcome (offer accepted) — v9 Monochrome
  // reserves green for verified/success states.
  hired: "accepted",
};

/**
 * Offer status → StatusBadge tone (ADR-0007). Color is always paired with the
 * text label, never the sole signal.
 */
export const OFFER_STATUS_TONE: Record<string, StatusTone> = {
  draft: "draft",
  pending_approval: "pending",
  approved: "active",
  sent: "offer",
  accepted: "accepted",
  declined: "rejected",
  expired: "closed",
  rescinded: "closed",
};

export const REVEAL_STATUS_TONE: Record<string, StatusTone> = {
  none: "draft",
  pending: "pending",
  accepted: "accepted",
  declined: "rejected",
  expired: "closed",
};

/**
 * Localized status labels for applications. Backend pairs each status with a
 * vi-only `status_label`; we map the stable enum CODE through next-intl for
 * vi/en parity and fall back to the server label, then the raw code.
 */
export function useApplicationLabels() {
  const t = useTranslations("applications.status");
  const tr = useTranslations("applications.revealStatus");

  return {
    status(
      code: ApplicationStatus | string | null | undefined,
      serverLabel?: string | null,
    ): string {
      if (!code) return serverLabel || "—";
      if (t.has(code)) return t(code);
      return serverLabel || code;
    },
    reveal(
      code: RevealStatus | string | null | undefined,
      serverLabel?: string | null,
    ): string {
      if (!code) return serverLabel || "—";
      if (tr.has(code)) return tr(code);
      return serverLabel || code;
    },
  };
}

/**
 * Localized label for a coded rejection reason. Partner-only surface — the
 * backend never returns reason/note on student projections, so this is never
 * rendered on student screens.
 */
export function useRejectionReasonLabel() {
  const t = useTranslations("candidates.rejectReasons");
  return (code: string | null | undefined): string => {
    if (!code) return "—";
    return t.has(code) ? t(code) : code;
  };
}

/**
 * Interview status -> StatusBadge tone. Color is always paired with the text
 * label, never the sole signal.
 */
export const INTERVIEW_STATUS_TONE: Record<string, StatusTone> = {
  scheduled: "active",
  completed: "accepted",
  cancelled: "closed",
  no_show: "rejected",
  rescheduled: "pending",
};

/**
 * Localized labels for interview mode + status codes (ADR-0006). The backend
 * supplies a vi `mode_label`; we prefer the frontend i18n copy for vi/en parity,
 * then fall back to the server label, then the raw code. Interview `status` has
 * no server label, so it is localized here.
 */
export function useInterviewLabels() {
  const tm = useTranslations("interviews.mode");
  const ts = useTranslations("interviews.status");

  return {
    mode(code: string | null | undefined, serverLabel?: string | null): string {
      if (!code) return serverLabel || "—";
      if (tm.has(code)) return tm(code);
      return serverLabel || code;
    },
    status(code: string | null | undefined): string {
      if (!code) return "—";
      if (ts.has(code)) return ts(code);
      return code;
    },
  };
}

/**
 * Localized labels for offer status + salary-period codes (ADR-0007). The
 * backend pairs each status with a vi `status_label`; we prefer the frontend
 * i18n copy for vi/en parity, then fall back to the server label, then the raw
 * code (raw codes never reach end users).
 */
export function useOfferLabels() {
  const ts = useTranslations("offers.status");
  const tp = useTranslations("offers.period");

  return {
    status(
      code: string | null | undefined,
      serverLabel?: string | null,
    ): string {
      if (!code) return serverLabel || "—";
      if (ts.has(code)) return ts(code);
      return serverLabel || code;
    },
    period(code: string | null | undefined): string {
      if (!code) return "—";
      if (tp.has(code)) return tp(code);
      return code;
    },
  };
}

/**
 * Localized labels for scorecard criteria + recommendation codes (ADR-0005).
 * Partner-internal — never rendered on any student surface. Prefers the stable
 * frontend i18n copy (vi/en parity); falls back to the server-provided label,
 * then the raw code. The backend currently presents labels in vi only, so the
 * i18n-first order keeps the English UI correct.
 */
export function useScorecardLabels() {
  const tc = useTranslations("scorecards.criteria");
  const tr = useTranslations("scorecards.recommendation");

  return {
    criterion(code: string, serverLabel?: string | null): string {
      if (tc.has(code)) return tc(code);
      return serverLabel || code;
    },
    recommendation(
      code: string | null | undefined,
      serverLabel?: string | null,
    ): string {
      if (!code) return serverLabel || "—";
      if (tr.has(code)) return tr(code);
      return serverLabel || code;
    },
  };
}
