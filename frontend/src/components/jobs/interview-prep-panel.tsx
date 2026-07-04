"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import {
  ArrowSquareOut,
  Brain,
  ChatsTeardrop,
  CheckCircle,
  Lightbulb,
  Sparkle,
  Warning,
  X,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { interviewPrepApi, type InterviewPrepResult, type InterviewQuestion } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  jobId: string;
}

type QuestionType = InterviewQuestion["type"];

type Phase =
  | { name: "idle" }
  | { name: "loading" }
  | { name: "ready"; result: InterviewPrepResult }
  | { name: "failed" };

const TYPE_ICON: Record<QuestionType, React.ElementType> = {
  behavioral: ChatsTeardrop,
  technical: Brain,
  situational: Lightbulb,
  motivation: Sparkle,
};

const TYPE_COLOR: Record<QuestionType, string> = {
  behavioral: "bg-[var(--blue-50)] text-[var(--brand-primary)]",
  technical: "bg-[var(--teal-50)] text-[var(--brand-teal)]",
  situational: "bg-[var(--teal-50)] text-[var(--brand-teal)]",
  motivation: "bg-[var(--amber-100)] text-[var(--amber-700)]",
};

/**
 * Inline interview prep panel for the public job detail student sidebar.
 * Read-only advisory only — never stored, never sent to the hiring partner.
 */
export function InterviewPrepPanel({ jobId }: Props) {
  const t = useTranslations("jobs.interviewPrep");
  const [phase, setPhase] = useState<Phase>({ name: "idle" });
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  async function generate() {
    setPhase({ name: "loading" });
    try {
      const result = await interviewPrepApi.generatePrep(jobId, {
        num_questions: 6,
      });
      setPhase({ name: "ready", result });
      setExpanded(new Set());
    } catch {
      setPhase({ name: "failed" });
    }
  }

  function toggleExpanded(num: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(num)) next.delete(num);
      else next.add(num);
      return next;
    });
  }

  if (phase.name === "idle") {
    return (
      <button
        type="button"
        onClick={generate}
        className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-4 py-2.5 text-sm font-semibold text-[var(--brand-primary)] transition hover:bg-[var(--surface-hover)] hover:border-[var(--brand-primary)]/50"
      >
        <Sparkle aria-hidden weight="duotone" className="size-4 shrink-0" />
        {t("generate")}
      </button>
    );
  }

  if (phase.name === "loading") {
    return (
      <div className="mt-3 flex items-center justify-center gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-4 py-3 ">
        <span
          aria-hidden
          className="size-4 animate-spin rounded-full border-2 border-[var(--brand-primary)] border-t-transparent"
        />
        <span className="text-sm text-[var(--text-muted)]">{t("generating")}</span>
      </div>
    );
  }

  if (phase.name === "failed") {
    return (
      <div className="mt-3 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-4 py-3 ">
        <div className="flex items-center gap-2 text-sm text-[var(--brand-red)]">
          <Warning aria-hidden weight="fill" className="size-4 shrink-0" />
          {t("error")}
        </div>
        <button
          type="button"
          onClick={() => setPhase({ name: "idle" })}
          className="mt-2 text-xs font-medium text-[var(--brand-primary)] underline hover:no-underline"
        >
          {t("retry")}
        </button>
      </div>
    );
  }

  const { result } = phase;
  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-[var(--glass-surface-light)] shadow-[0_2px_12px_rgba(11,34,57,0.06)]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[var(--border-default)] px-3.5 py-2.5">
        <div className="flex items-center gap-2">
          <span className="flex size-5 shrink-0 items-center justify-center rounded-md icon-chip-info shadow-sm">
            <Sparkle aria-hidden weight="duotone" className="size-3 text-white" />
          </span>
          <span className="text-xs font-bold text-[var(--text-primary)]">
            {t("panelTitle")}
          </span>
        </div>
        <button
          type="button"
          aria-label={t("close")}
          onClick={() => setPhase({ name: "idle" })}
          className="rounded-lg p-1 text-[var(--text-muted)] hover:bg-[var(--glass-surface-light)]"
        >
          <X aria-hidden weight="bold" className="size-3.5" />
        </button>
      </div>

      {/* Fallback notice */}
      {result.is_fallback && (
        <div className="border-b border-[var(--border-default)] bg-[var(--amber-100)] px-3.5 py-2 text-xs text-[var(--amber-700)]">
          {t("fallbackNote")}
        </div>
      )}

      {/* Questions list */}
      <div className="divide-y divide-[var(--border-default)]">
        {result.questions.map((q) => {
          const isOpen = expanded.has(q.number);
          const TypeIcon = TYPE_ICON[q.type] ?? ChatsTeardrop;
          const typeColor = TYPE_COLOR[q.type] ?? TYPE_COLOR.behavioral;
          return (
            <div key={q.number}>
              <button
                type="button"
                className="flex w-full items-start gap-2.5 px-3.5 py-2.5 text-left hover:bg-[var(--glass-surface-light)]"
                onClick={() => toggleExpanded(q.number)}
                aria-expanded={isOpen}
              >
                <span
                  className={cn(
                    "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-md text-[10px] font-bold",
                    typeColor,
                  )}
                >
                  {q.number}
                </span>
                <span className="flex-1 text-xs font-medium leading-relaxed text-[var(--text-primary)]">
                  {q.question}
                </span>
                <span
                  className={cn(
                    "ml-auto flex size-5 shrink-0 items-center justify-center rounded-md",
                    typeColor,
                  )}
                >
                  <TypeIcon aria-hidden weight="duotone" className="size-3.5" />
                </span>
              </button>

              {isOpen && (
                <div className="space-y-2 border-t border-[var(--border-default)] bg-[var(--glass-surface-light)] px-3.5 py-3">
                  <Detail
                    icon={CheckCircle}
                    label={t("hintLabel")}
                    text={q.hint}
                    iconClass="text-[var(--brand-teal)]"
                  />
                  <Detail
                    icon={Lightbulb}
                    label={t("rubricLabel")}
                    text={q.rubric}
                    iconClass="text-[var(--amber-600)]"
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Prep tips */}
      {result.prep_tips && (
        <div className="border-t border-[var(--border-default)] px-3.5 py-3">
          <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-[var(--text-muted)]">
            {t("prepTipsLabel")}
          </p>
          <p className="text-xs leading-relaxed text-[var(--text-secondary)]">
            {result.prep_tips}
          </p>
        </div>
      )}

      {/* Footer: disclaimer + full simulator link */}
      <div className="flex items-center justify-between border-t border-[var(--border-default)] px-3.5 py-2">
        <p className="text-[10px] text-[var(--text-muted)]">{t("disclaimer")}</p>
        <Link
          href={`/jobs/${jobId}/interview-sim`}
          className="ml-3 flex shrink-0 items-center gap-1 text-[10px] font-bold text-[var(--brand-primary)] hover:underline"
        >
          {t("openSimulatorCta")}
          <ArrowSquareOut weight="bold" className="size-3" aria-hidden />
        </Link>
      </div>
    </div>
  );
}

function Detail({
  icon: Icon,
  label,
  text,
  iconClass,
}: {
  icon: React.ElementType;
  label: string;
  text: string;
  iconClass: string;
}) {
  return (
    <div className="flex items-start gap-1.5">
      <Icon aria-hidden weight="duotone" className={cn("mt-0.5 size-3.5 shrink-0", iconClass)} />
      <div className="min-w-0">
        <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-muted)]">
          {label}
        </p>
        <p className="text-xs leading-relaxed text-[var(--text-secondary)]">{text}</p>
      </div>
    </div>
  );
}
