"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import {
  ArrowClockwise,
  CheckCircle,
  PlusCircle,
  Sparkle,
  Warning,
  X,
} from "@phosphor-icons/react";
import { cvApi, type CvAiSuggestion, type CvImprovementHandoff } from "@/lib/api";
import { improvementIdempotencyKey } from "@/lib/jobs/job-intelligence";
import { sectionsToText } from "@/components/cv/ai-assist/utils";

type Phase =
  | { name: "idle" }
  | { name: "requesting" }
  | { name: "diff"; suggestion: CvAiSuggestion }
  | { name: "accepting"; suggestion: CvAiSuggestion }
  | { name: "done" }
  | { name: "failed" };

/**
 * One confirmation-gated "apply this improvement" hand-off (a fit gap → CV
 * Studio pending diff). Clicking "Apply" POSTs the backend-built edit command to
 * open a PENDING diff — it NEVER auto-mutates the CV. The student then explicitly
 * accepts or discards the diff; accepting saves a new (audited) CV version.
 */
export function ImprovementRow({
  handoff,
  onApplied,
}: {
  handoff: CvImprovementHandoff;
  onApplied?: () => void;
}) {
  const t = useTranslations("jobs.studentIntel.improve");
  const [phase, setPhase] = useState<Phase>({ name: "idle" });
  const [factConfirmed, setFactConfirmed] = useState(false);
  // Stable per-hand-off idempotency key: a retried Apply de-dupes to the same
  // pending suggestion instead of stacking new drafts.
  const idemKey = useRef(
    improvementIdempotencyKey(handoff.cv_id, handoff.skill),
  ).current;

  async function requestDiff() {
    setPhase({ name: "requesting" });
    setFactConfirmed(false);
    try {
      const suggestion = await cvApi.requestAiEditCommand(handoff.cv_id, {
        instruction: handoff.request.instruction,
        idempotency_key: idemKey,
      });
      setPhase({ name: "diff", suggestion });
    } catch {
      setPhase({ name: "failed" });
    }
  }

  async function accept(suggestion: CvAiSuggestion) {
    setPhase({ name: "accepting", suggestion });
    try {
      await cvApi.acceptAiSuggestion(handoff.cv_id, suggestion.suggestion_id, {
        fact_confirmation: factConfirmed,
        idempotency_key: `${idemKey}:accept`,
      });
      setPhase({ name: "done" });
      onApplied?.();
    } catch {
      setPhase({ name: "diff", suggestion });
    }
  }

  async function reject(suggestion: CvAiSuggestion) {
    setPhase({ name: "idle" });
    try {
      await cvApi.rejectAiSuggestion(handoff.cv_id, suggestion.suggestion_id);
    } catch {
      // Best-effort discard; the pending suggestion expires server-side.
    }
  }

  if (phase.name === "done") {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-[var(--teal-600)]/25 bg-[var(--teal-50)] px-3.5 py-2.5 text-xs font-medium text-[var(--teal-700)]">
        <CheckCircle aria-hidden weight="fill" className="size-4 shrink-0" />
        {t("accepted")}
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-3.5 py-3">
      <div className="flex items-start gap-2.5">
        <span className="flex size-6 shrink-0 items-center justify-center rounded-md icon-chip-warning">
          <PlusCircle aria-hidden weight="duotone" className="size-3.5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-[var(--text-primary)]">
            {handoff.skill}
          </p>
          {handoff.rationale && (
            <p className="mt-0.5 text-[11px] leading-relaxed text-[var(--text-muted)]">
              {handoff.rationale}
            </p>
          )}
        </div>
        {(phase.name === "idle" || phase.name === "failed") && (
          <button
            type="button"
            onClick={requestDiff}
            className="shrink-0 rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-2.5 py-1 text-[11px] font-semibold text-[var(--brand-primary)] outline-none transition-colors hover:bg-[var(--surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
          >
            <span className="flex items-center gap-1">
              {phase.name === "failed" ? (
                <ArrowClockwise aria-hidden weight="bold" className="size-3" />
              ) : (
                <Sparkle aria-hidden weight="duotone" className="size-3" />
              )}
              {phase.name === "failed" ? t("retry") : t("apply")}
            </span>
          </button>
        )}
        {phase.name === "requesting" && (
          <span
            aria-hidden
            className="size-4 shrink-0 animate-spin rounded-full border-2 border-[var(--brand-primary)] border-t-transparent"
          />
        )}
      </div>

      {phase.name === "failed" && (
        <p className="mt-2 flex items-center gap-1.5 text-[11px] text-[var(--brand-red)]">
          <Warning aria-hidden weight="fill" className="size-3.5 shrink-0" />
          {t("error")}
        </p>
      )}

      {phase.name === "idle" && (
        <p className="mt-2 text-[10px] leading-relaxed text-[var(--text-muted)]">
          {t("confirmHint")}
        </p>
      )}

      {(phase.name === "diff" || phase.name === "accepting") && (
        <DiffCard
          suggestion={phase.suggestion}
          factConfirmed={factConfirmed}
          onFactConfirm={setFactConfirmed}
          accepting={phase.name === "accepting"}
          onAccept={() => accept(phase.suggestion)}
          onReject={() => reject(phase.suggestion)}
          t={t}
        />
      )}
    </div>
  );
}

function DiffCard({
  suggestion,
  factConfirmed,
  onFactConfirm,
  accepting,
  onAccept,
  onReject,
  t,
}: {
  suggestion: CvAiSuggestion;
  factConfirmed: boolean;
  onFactConfirm: (v: boolean) => void;
  accepting: boolean;
  onAccept: () => void;
  onReject: () => void;
  t: ReturnType<typeof useTranslations>;
}) {
  const diff = suggestion.diff;
  const needsConfirm = diff?.requires_fact_confirmation ?? false;
  const canAccept = !needsConfirm || factConfirmed;
  const beforeText = sectionsToText(diff?.before);
  const afterText = sectionsToText(diff?.after);

  return (
    <div className="mt-3 space-y-2.5 border-t border-[var(--border-default)] pt-3">
      {diff?.summary && (
        <p className="text-xs leading-relaxed text-[var(--text-secondary)]">
          {diff.summary}
        </p>
      )}
      {beforeText && (
        <div className="space-y-1">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("before")}
          </span>
          <pre className="max-h-28 overflow-y-auto whitespace-pre-wrap break-words rounded-lg border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3 py-2 font-sans text-xs text-[var(--text-secondary)] line-through opacity-70">
            {beforeText}
          </pre>
        </div>
      )}
      {afterText && (
        <div className="space-y-1">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("after")}
          </span>
          <pre className="max-h-36 overflow-y-auto whitespace-pre-wrap break-words rounded-lg border border-[var(--brand-primary)]/30 bg-[var(--surface-card)] px-3 py-2 font-sans text-xs text-[var(--text-primary)] ring-1 ring-inset ring-[var(--brand-primary)]/15">
            {afterText}
          </pre>
        </div>
      )}
      {needsConfirm && (
        <label className="flex cursor-pointer items-start gap-2 rounded-lg border border-[var(--amber-500)]/40 bg-[var(--amber-50)] px-3 py-2">
          <input
            type="checkbox"
            checked={factConfirmed}
            onChange={(e) => onFactConfirm(e.target.checked)}
            className="mt-0.5 size-3.5 shrink-0 rounded accent-[var(--brand-primary)]"
          />
          <span className="text-[11px] leading-relaxed text-[var(--text-secondary)]">
            {t("factConfirm")}
          </span>
        </label>
      )}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onReject}
          disabled={accepting}
          className="flex items-center gap-1 rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-2.5 py-1.5 text-[11px] font-medium text-[var(--text-primary)] outline-none transition-colors hover:bg-[var(--surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30 disabled:opacity-40"
        >
          <X aria-hidden weight="bold" className="size-3" />
          {t("reject")}
        </button>
        <button
          type="button"
          onClick={onAccept}
          disabled={!canAccept || accepting}
          className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-[var(--brand-primary)] px-3 py-1.5 text-[11px] font-semibold text-[var(--text-inverted)] outline-none transition-opacity hover:opacity-90 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40 disabled:opacity-40"
        >
          {accepting ? (
            <span
              aria-hidden
              className="size-3.5 animate-spin rounded-full border-2 border-[var(--text-inverted)] border-t-transparent"
            />
          ) : (
            <CheckCircle aria-hidden weight="fill" className="size-3.5" />
          )}
          {accepting ? t("accepting") : t("accept")}
        </button>
      </div>
    </div>
  );
}
