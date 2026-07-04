"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import {
  CheckCircle,
  Sparkle,
  Warning,
  X,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { jobsApi, type JdDraftInputs } from "@/lib/api";

interface Props {
  /** When present, uses the anchored endpoint; otherwise uses standalone. */
  jobId?: string;
  /** Current form values to pass as context inputs. */
  formInputs: JdDraftInputs;
  /** Called with the accepted draft text so the parent can fill the field. */
  onAccept: (draft: string) => void;
}

type Phase =
  | { name: "idle" }
  | { name: "loading" }
  | { name: "ready"; draft: string }
  | { name: "failed"; message: string };

/**
 * "Generate with AI" button + inline draft review for the JD description field.
 * Advisory only — partners review and explicitly accept before the draft fills
 * the form. No auto-apply, no publish without confirmation.
 */
export function JdWriterButton({ jobId, formInputs, onAccept }: Props) {
  const t = useTranslations("jobs.aiJd");
  const [phase, setPhase] = useState<Phase>({ name: "idle" });

  async function generate() {
    setPhase({ name: "loading" });
    try {
      const result = jobId
        ? await jobsApi.aiDraftDescription(jobId, formInputs)
        : await jobsApi.aiDraftDescriptionStandalone(formInputs);
      setPhase({ name: "ready", draft: result.draft });
    } catch {
      setPhase({ name: "failed", message: t("error") });
    }
  }

  function handleAccept() {
    if (phase.name !== "ready") return;
    onAccept(phase.draft);
    setPhase({ name: "idle" });
  }

  if (phase.name === "idle") {
    return (
      <button
        type="button"
        onClick={generate}
        className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--ai-accent)]/30 bg-[var(--ai-accent-soft)] px-3 py-1.5 text-xs font-semibold text-[var(--ai-accent)] transition hover:border-[var(--ai-accent)]/50 hover:bg-[var(--teal-100)]"
      >
        <span className="flex size-4 shrink-0 items-center justify-center rounded icon-chip-success shadow-sm">
          <Sparkle aria-hidden weight="duotone" className="size-2.5 text-white" />
        </span>
        {t("generate")}
      </button>
    );
  }

  if (phase.name === "loading") {
    return (
      <div className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
        <svg
          aria-hidden
          className="size-3.5 animate-spin text-[var(--brand-primary)]"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        {t("generating")}
      </div>
    );
  }

  if (phase.name === "failed") {
    return (
      <div className="flex items-center gap-1.5 text-xs text-[var(--brand-red)]">
        <Warning aria-hidden weight="fill" className="size-3.5 shrink-0" />
        {phase.message}
        <button
          type="button"
          onClick={() => setPhase({ name: "idle" })}
          className="ml-1 underline hover:no-underline"
        >
          {t("retry")}
        </button>
      </div>
    );
  }

  // phase === "ready" — show draft review panel (AI surface standard)
  return (
    <div className="mt-2 space-y-2">
      <div className={cn(
        "rounded-xl border overflow-hidden shadow-[0_2px_16px_rgba(109,40,217,0.08)]",
        "border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white/60 ",
      )}>
        <div className="flex items-center justify-between border-b border-[var(--border-default)] px-3.5 py-2.5">
          <div className="flex items-center gap-2">
            <span className="flex size-5 shrink-0 items-center justify-center rounded-md icon-chip-info shadow-sm">
              <Sparkle aria-hidden weight="duotone" className="size-3 text-white" />
            </span>
            <span className="text-xs font-bold text-[var(--text-primary)]">
              {t("draftTitle")}
            </span>
          </div>
          <button
            type="button"
            onClick={() => setPhase({ name: "idle" })}
            aria-label={t("discard")}
            className="rounded-lg p-1 text-[var(--text-muted)] outline-none hover:bg-white/60 focus-visible:ring-1 focus-visible:ring-[var(--ai-accent)]/50"
          >
            <X aria-hidden weight="bold" className="size-3.5" />
          </button>
        </div>
        <div className="max-h-56 overflow-y-auto px-3.5 py-3">
          <pre className="whitespace-pre-wrap break-words font-sans text-sm text-[var(--text-secondary)]">
            {phase.draft}
          </pre>
        </div>
        <div className="flex items-center justify-between border-t border-[var(--border-default)] px-3.5 py-2.5">
          <p className="text-[0.7rem] text-[var(--text-muted)]">{t("disclaimer")}</p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setPhase({ name: "idle" })}
              className="rounded-lg px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] outline-none hover:bg-white/60 focus-visible:ring-1 focus-visible:ring-[var(--ai-accent)]/50"
            >
              {t("discard")}
            </button>
            <button
              type="button"
              onClick={handleAccept}
              className="inline-flex items-center gap-1.5 rounded-lg icon-chip-success px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ai-accent)]/50"
            >
              <CheckCircle aria-hidden weight="duotone" className="size-3.5" />
              {t("useDraft")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
