"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { ShieldCheck, ArrowCounterClockwise } from "@phosphor-icons/react";
import { useToast } from "@/components/ui";
import { discoveryApi } from "@/lib/api";

/**
 * Honest privacy affordance for the first-party discovery session (spec §3).
 * Explains, in plain language, that we store only COARSE interests to personalize
 * recommendations — never PII — and offers a one-click reset that clears the
 * stored signals server-side (`POST /discovery/session/reset`). Feedback is a
 * toast, never `alert()`/`confirm()`.
 */
export function DiscoveryPrivacyNote() {
  const t = useTranslations("discovery.privacy");
  const toast = useToast();
  const [resetting, setResetting] = useState(false);

  async function handleReset() {
    if (resetting) return;
    setResetting(true);
    try {
      await discoveryApi.sessionReset(false);
      toast.show({ tone: "success", title: t("resetDone"), description: t("resetDoneBody") });
    } catch {
      toast.show({ tone: "error", title: t("resetFailed"), description: t("resetFailedBody") });
    } finally {
      setResetting(false);
    }
  }

  return (
    <div className="mt-10 flex flex-col gap-3 rounded-xl border border-white/50 bg-white/60 px-4 py-3 text-sm backdrop-blur-sm sm:flex-row sm:items-center sm:justify-between">
      <p className="flex items-start gap-2 text-[var(--text-secondary)]">
        <ShieldCheck
          aria-hidden
          weight="duotone"
          className="mt-0.5 size-5 shrink-0 text-[var(--brand-teal)]"
        />
        <span>{t("note")}</span>
      </p>
      <button
        type="button"
        onClick={handleReset}
        disabled={resetting}
        className="inline-flex shrink-0 items-center gap-1.5 self-start rounded-lg border border-white/60 bg-white/80 px-3 py-1.5 text-sm font-semibold text-[var(--text-primary)] outline-none backdrop-blur-sm transition-all hover:border-[var(--brand-primary)]/60 hover:text-[var(--brand-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30 disabled:cursor-not-allowed disabled:opacity-60 sm:self-auto"
      >
        <ArrowCounterClockwise aria-hidden weight="bold" className="size-4" />
        {resetting ? t("resetting") : t("resetCta")}
      </button>
    </div>
  );
}
