"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle,
  MinusCircle,
  Sparkle,
  Warning,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react";
import { applicationsApi } from "@/lib/api";

const SUITABILITY_STYLES = {
  strong: {
    Icon: CheckCircle,
    label: "strong",
    className:
      "text-emerald-700 bg-emerald-50 border-emerald-200 ring-emerald-100",
  },
  moderate: {
    Icon: MinusCircle,
    label: "moderate",
    className: "text-amber-700 bg-amber-50 border-amber-200 ring-amber-100",
  },
  weak: {
    Icon: XCircle,
    label: "weak",
    className: "text-red-700 bg-red-50 border-red-200 ring-red-100",
  },
} as const;

interface Props {
  applicationId: string;
}

export function AiScreeningBrief({ applicationId }: Props) {
  const t = useTranslations("applications.screeningBrief");
  const [enabled, setEnabled] = useState(false);

  const query = useQuery({
    queryKey: ["applications", applicationId, "ai-screening-brief"],
    queryFn: () => applicationsApi.getScreeningBrief(applicationId),
    enabled,
    staleTime: 10 * 60 * 1000,
    retry: false,
  });

  const brief = query.data;

  if (!enabled) {
    return (
      <button
        type="button"
        onClick={() => setEnabled(true)}
        className="inline-flex items-center gap-1.5 rounded-full border border-[var(--ai-accent)]/40 bg-[var(--ai-accent-soft)] px-3 py-1.5 text-xs font-semibold text-[var(--ai-accent)] outline-none transition-colors hover:bg-[var(--ai-accent)]/15 focus-visible:ring-2 focus-visible:ring-[var(--ai-accent)]/40"
      >
        <Sparkle aria-hidden weight="fill" className="size-3.5" />
        {t("cta")}
      </button>
    );
  }

  if (query.isPending) {
    return (
      <div className="flex items-center gap-2 text-sm text-[var(--ai-accent)]">
        <span className="size-4 animate-spin rounded-full border-2 border-[var(--ai-accent)]/30 border-t-[var(--ai-accent)]" />
        {t("loading")}
      </div>
    );
  }

  if (query.isError || !brief) {
    return (
      <div className="flex items-center gap-2 text-sm text-[var(--brand-red)]">
        <WarningCircle aria-hidden weight="fill" className="size-4 shrink-0" />
        {t("error")}
      </div>
    );
  }

  if (brief.is_fallback || brief.bullets.length === 0) {
    return (
      <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
        <Warning aria-hidden weight="fill" className="size-4 shrink-0 text-amber-500" />
        {t("unavailable")}
      </div>
    );
  }

  const suitability = brief.suitability
    ? SUITABILITY_STYLES[brief.suitability]
    : null;

  return (
    <div className="rounded-xl border border-white/60 bg-[var(--ai-accent-soft)]/60 p-4 backdrop-blur-sm">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-semibold text-[var(--ai-accent)]">
          <span className="flex size-5 shrink-0 items-center justify-center rounded-md icon-chip-info shadow-sm">
            <Sparkle aria-hidden weight="duotone" className="size-3 text-white" />
          </span>
          {t("title")}
        </div>
        {suitability && (
          <span
            className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${suitability.className}`}
          >
            <suitability.Icon aria-hidden weight="fill" className="size-3" />
            {t(`suitability.${brief.suitability}`)}
          </span>
        )}
      </div>

      {/* Bullets */}
      <ul className="mt-3 space-y-1.5">
        {brief.bullets.map((bullet, i) => (
          <li key={i} className="flex items-start gap-2 text-sm text-[var(--text-secondary)]">
            <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-[var(--ai-accent)]/60" />
            {bullet}
          </li>
        ))}
      </ul>

      {/* Disclaimer */}
      <p className="mt-3 text-[11px] text-[var(--text-muted)]">
        {t("disclaimer")}
      </p>
    </div>
  );
}
