"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import {
  Brain,
  CheckCircle,
  Sparkle,
  Warning,
} from "@phosphor-icons/react";
import { applicationsApi, SCORECARD_CRITERIA, type ScorecardAiSuggestion, type ScorecardRecommendation } from "@/lib/api";
import { Modal } from "@/components/ui";
import { cn } from "@/lib/utils";

interface Props {
  applicationId: string;
  jobTitle?: string;
  interviewStage?: string;
  /** Called when the partner applies all AI suggestions. */
  onApply: (
    scores: Record<string, number>,
    recommendation: ScorecardRecommendation | "",
    reasoning: string,
  ) => void;
}

type Phase =
  | { name: "notes" }
  | { name: "loading" }
  | { name: "ready"; suggestion: ScorecardAiSuggestion }
  | { name: "failed" };

const CONFIDENCE_COLOR: Record<string, string> = {
  high: "text-[var(--brand-teal)]",
  medium: "text-[var(--amber-700)]",
  low: "text-[var(--brand-red)]",
};

/**
 * AI Scorecard Suggest trigger + modal.
 * human_review consent tier — AI output is a DRAFT that the partner explicitly
 * applies. The AI never writes to the scorecard directly.
 */
export function ScorecardAiSuggestButton({
  applicationId,
  jobTitle,
  interviewStage,
  onApply,
}: Props) {
  const t = useTranslations("scorecards.aiSuggest");
  const tCriteria = useTranslations("scorecards.criteria");
  const tRec = useTranslations("scorecards.recommendation");
  const [open, setOpen] = useState(false);
  const [notes, setNotes] = useState("");
  const [phase, setPhase] = useState<Phase>({ name: "notes" });

  function handleOpen() {
    setPhase({ name: "notes" });
    setOpen(true);
  }

  function handleClose() {
    setOpen(false);
  }

  async function handleGenerate() {
    if (!notes.trim()) return;
    setPhase({ name: "loading" });
    try {
      const result = await applicationsApi.aiScorecardSuggest(applicationId, {
        notes: notes.trim(),
        job_title: jobTitle,
        interview_stage: interviewStage,
      });
      setPhase({ name: "ready", suggestion: result });
    } catch {
      setPhase({ name: "failed" });
    }
  }

  function handleApplyAll() {
    if (phase.name !== "ready") return;
    const { suggestion } = phase;
    const scores: Record<string, number> = {};
    for (const key of SCORECARD_CRITERIA) {
      const score = suggestion.criteria[key]?.score;
      if (typeof score === "number") scores[key] = score;
    }
    const rec =
      suggestion.recommendation &&
      (["strong_yes", "yes", "no", "strong_no"] as const).includes(
        suggestion.recommendation as ScorecardRecommendation,
      )
        ? (suggestion.recommendation as ScorecardRecommendation)
        : ("" as const);
    onApply(scores, rec, suggestion.overall_reasoning);
    handleClose();
  }

  return (
    <>
      <button
        type="button"
        onClick={handleOpen}
        className="inline-flex items-center gap-1.5 rounded-lg border border-white/60 bg-white/72 px-2.5 py-1 text-xs font-medium text-[var(--brand-primary)] backdrop-blur-sm transition hover:bg-white/90 hover:border-[var(--brand-primary)]/50"
      >
        <Brain aria-hidden weight="duotone" className="size-3.5" />
        {t("button")}
      </button>

      <Modal
        open={open}
        onClose={handleClose}
        title={t("panelTitle")}
        size="md"
      >
        {phase.name === "notes" && (
          <div className="space-y-4 p-4">
            <div>
              <label
                htmlFor="sc-ai-notes"
                className="mb-1.5 block text-xs font-semibold text-[var(--text-secondary)]"
              >
                {t("notesLabel")}
              </label>
              <textarea
                id="sc-ai-notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder={t("notesPlaceholder")}
                rows={8}
                className="w-full resize-none rounded-xl border border-white/60 bg-white/80 backdrop-blur-sm px-3 py-2.5 text-sm text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-muted)] focus:border-[var(--brand-primary)]/50 focus:bg-white/95 focus:ring-2 focus:ring-[var(--brand-primary)]/30"
              />
            </div>
            <p className="text-[11px] text-[var(--text-muted)]">
              {t("disclaimer")}
            </p>
            <div className="flex justify-end gap-2 border-t border-white/40 pt-3">
              <button
                type="button"
                onClick={handleClose}
                className="rounded-lg px-3 py-1.5 text-sm font-medium text-[var(--text-secondary)] hover:bg-white/60"
              >
                {t("discard")}
              </button>
              <button
                type="button"
                onClick={() => void handleGenerate()}
                disabled={!notes.trim()}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--brand-primary)] px-3 py-1.5 text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
              >
                <Sparkle aria-hidden weight="duotone" className="size-4" />
                {t("button")}
              </button>
            </div>
          </div>
        )}

        {phase.name === "loading" && (
          <div className="flex flex-col items-center gap-3 py-12">
            <span
              aria-hidden
              className="size-8 animate-spin rounded-full border-[3px] border-[var(--brand-primary)] border-t-transparent"
            />
            <p className="text-sm text-[var(--text-muted)]">{t("generating")}</p>
          </div>
        )}

        {phase.name === "failed" && (
          <div className="p-4">
            <div className="flex items-center gap-2 rounded-xl bg-[var(--red-50)] p-3 text-sm text-[var(--brand-red)]">
              <Warning aria-hidden weight="fill" className="size-4 shrink-0" />
              {t("error")}
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <button type="button" onClick={handleClose} className="text-sm text-[var(--text-secondary)] hover:underline">
                {t("discard")}
              </button>
              <button
                type="button"
                onClick={() => setPhase({ name: "notes" })}
                className="text-sm font-medium text-[var(--brand-primary)] underline hover:no-underline"
              >
                {t("retry")}
              </button>
            </div>
          </div>
        )}

        {phase.name === "ready" && (
          <div className="space-y-0">
            {/* Confidence badge */}
            {phase.suggestion.is_fallback ? (
              <div className="border-b border-white/40 bg-[var(--amber-100)] px-4 py-2 text-xs text-[var(--amber-700)]">
                {t("fallbackNote")}
              </div>
            ) : (
              <div className="flex items-center gap-2 border-b border-white/40 px-4 py-2">
                <CheckCircle aria-hidden weight="fill" className="size-3.5 text-[var(--brand-teal)]" />
                <span
                  className={cn(
                    "text-xs font-medium",
                    CONFIDENCE_COLOR[phase.suggestion.confidence] ?? "text-[var(--text-muted)]",
                  )}
                >
                  {t(`confidence.${phase.suggestion.confidence}`)}
                </span>
              </div>
            )}

            {/* Per-criterion suggestions */}
            <div className="divide-y divide-white/40 px-4">
              {SCORECARD_CRITERIA.map((key) => {
                const suggestion = phase.suggestion.criteria[key];
                const score = suggestion?.score;
                return (
                  <div key={key} className="flex items-start gap-3 py-3">
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-bold text-[var(--text-primary)]">
                        {tCriteria(key)}
                      </p>
                      {suggestion?.reasoning && (
                        <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                          {suggestion.reasoning}
                        </p>
                      )}
                    </div>
                    <div className="shrink-0">
                      {typeof score === "number" ? (
                        <span className="inline-flex items-center gap-0.5 rounded-lg bg-[var(--brand-primary)] px-2 py-0.5 text-xs font-bold text-white">
                          {score}/5
                        </span>
                      ) : (
                        <span className="text-xs text-[var(--text-muted)]">
                          {t("noScore")}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Overall recommendation */}
            {phase.suggestion.recommendation && (
              <div className="border-t border-white/40 bg-white/40 px-4 py-3">
                <p className="text-xs text-[var(--text-muted)]">
                  {tRec(phase.suggestion.recommendation)}
                </p>
                {phase.suggestion.overall_reasoning && (
                  <p className="mt-1 text-xs text-[var(--text-secondary)]">
                    {phase.suggestion.overall_reasoning}
                  </p>
                )}
              </div>
            )}

            {/* Disclaimer + actions */}
            <div className="border-t border-white/40 px-4 pb-4 pt-3">
              <p className="mb-3 text-[11px] text-[var(--text-muted)]">
                {t("disclaimer")}
              </p>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={handleClose}
                  className="rounded-lg px-3 py-1.5 text-sm font-medium text-[var(--text-secondary)] hover:bg-white/60"
                >
                  {t("discard")}
                </button>
                <button
                  type="button"
                  onClick={handleApplyAll}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--brand-primary)] px-3 py-1.5 text-sm font-semibold text-white transition hover:opacity-90"
                >
                  <CheckCircle aria-hidden weight="duotone" className="size-4" />
                  {t("applyAll")}
                </button>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}
