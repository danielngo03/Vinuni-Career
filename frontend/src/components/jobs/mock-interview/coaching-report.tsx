"use client";

import { useEffect, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import {
  ArrowClockwise,
  Article,
  Barbell,
  BookOpen,
  CheckCircle,
  FilePdf,
  GraduationCap,
  Lightbulb,
  Notepad,
  PlayCircle,
  Sparkle,
  TrendUp,
  Warning,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui";
import {
  normalizeGap,
  type CoachingReport,
  type MockInterviewCoverage,
  type MockInterviewLearningSuggestion,
  type MockInterviewRound,
} from "@/lib/api";
import { usePrefersReducedMotion } from "@/lib/hooks/use-mount-animation";
import { cn } from "@/lib/utils";
import { CoverageReport } from "./coverage-progress";
import { RoundStepper } from "./round-indicator";

/**
 * Renders the score-free coaching report. There is deliberately NO score,
 * rating, or percentage anywhere — mock interview is formative practice.
 * Sections reveal gently on scroll (static under reduced motion).
 *
 * When {@link printable} (the default), the report is marked as the print
 * region and gains a "Download PDF" action (a print-scoped `window.print()`,
 * see globals.css `@media print`) plus an optional "Practice again" link when
 * {@link jobId} is supplied. Admin/read-only embeds pass `printable={false}`.
 */
export function CoachingReport({
  report,
  coverage,
  rounds,
  currentRound,
  jobId,
  jobTitle,
  completedAt,
  printable = true,
}: {
  report: CoachingReport | null;
  coverage?: MockInterviewCoverage | null;
  rounds?: MockInterviewRound[] | null;
  currentRound?: string | number | null;
  jobId?: string | null;
  jobTitle?: string | null;
  completedAt?: string | null;
  printable?: boolean;
}) {
  const t = useTranslations("jobs.mockInterview");
  const locale = useLocale();

  function handleDownloadPdf() {
    if (typeof window !== "undefined") window.print();
  }

  let printedDate: string | null = null;
  if (completedAt) {
    const d = new Date(completedAt);
    if (!Number.isNaN(d.getTime())) {
      printedDate = d.toLocaleDateString(locale, {
        year: "numeric",
        month: "long",
        day: "numeric",
      });
    }
  }
  const printMeta = [jobTitle?.trim(), printedDate].filter(Boolean).join(" · ");

  if (!report) {
    return (
      <div className="rounded-2xl border border-dashed border-[var(--border-strong)]/60 bg-[var(--surface-card)]/60 px-6 py-10 text-center">
        <span className="mx-auto mb-3 flex size-11 items-center justify-center rounded-2xl icon-chip-neutral">
          <Notepad aria-hidden weight="duotone" className="size-5" />
        </span>
        <h3 className="text-base font-semibold text-[var(--text-primary)]">
          {t("noReportTitle")}
        </h3>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          {t("noReportBody")}
        </p>
      </div>
    );
  }

  return (
    <div
      className="space-y-5"
      {...(printable ? { "data-mi-print-region": "" } : {})}
    >
      {printable && (
        <div data-mi-print-header className="hidden">
          <p className="text-base font-bold text-[var(--text-primary)]">
            {t("reportTitle")}
          </p>
          {printMeta && (
            <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
              {printMeta}
            </p>
          )}
        </div>
      )}

      <header className="flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-2xl icon-chip-primary shadow-sm">
          <Sparkle aria-hidden weight="duotone" className="size-5" />
        </span>
        <div className="min-w-0">
          <h2 className="text-lg font-bold tracking-tight text-[var(--text-primary)]">
            {t("reportTitle")}
          </h2>
          <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
            {t("reportSubtitle")}
          </p>
        </div>
      </header>

      {report.is_fallback && (
        <p className="flex items-start gap-2 rounded-xl border border-[var(--amber-600)]/30 bg-[var(--amber-50)] px-3.5 py-2.5 text-xs leading-relaxed text-[var(--amber-700)]">
          <Warning aria-hidden weight="fill" className="mt-0.5 size-4 shrink-0" />
          {t("fallbackNote")}
        </p>
      )}

      {rounds && rounds.length > 0 && (
        <Reveal>
          <section className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-5">
            <RoundStepper variant="card" rounds={rounds} current={currentRound} />
          </section>
        </Reveal>
      )}

      {report.overall_observations.trim() && (
        <Reveal>
          <section className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-5">
            <h3 className="kicker mb-2">{t("overallTitle")}</h3>
            <p className="whitespace-pre-line text-sm leading-7 text-[var(--text-secondary)]">
              {report.overall_observations}
            </p>
          </section>
        </Reveal>
      )}

      {coverage ? (
        <Reveal>
          <CoverageReport coverage={coverage} />
        </Reveal>
      ) : null}

      {report.strengths.length > 0 && (
        <Reveal>
          <section className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-5">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
              <CheckCircle aria-hidden weight="duotone" className="size-4 text-[var(--teal-600)]" />
              {t("strengthsTitle")}
            </h3>
            <ul className="space-y-2">
              {report.strengths.map((item, i) => (
                <li key={i} className="flex items-start gap-2.5 text-sm leading-relaxed text-[var(--text-secondary)]">
                  <span aria-hidden className="mt-1.5 size-1.5 shrink-0 rounded-full bg-[var(--teal-500)]" />
                  {item}
                </li>
              ))}
            </ul>
          </section>
        </Reveal>
      )}

      {report.gaps_to_work_on.length > 0 && (
        <Reveal>
          <section className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-5">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
              <TrendUp aria-hidden weight="duotone" className="size-4 text-[var(--amber-600)]" />
              {t("gapsTitle")}
            </h3>
            <ul className="space-y-3.5">
              {report.gaps_to_work_on.map((item, i) => {
                const gap = normalizeGap(item);
                if (!gap.text.trim() && gap.learning.length === 0) return null;
                return (
                  <li key={i}>
                    <div className="flex items-start gap-2.5 text-sm leading-relaxed text-[var(--text-secondary)]">
                      <span aria-hidden className="mt-1.5 size-1.5 shrink-0 rounded-full bg-[var(--amber-500)]" />
                      <span className="min-w-0">{gap.text}</span>
                    </div>
                    {gap.learning.length > 0 && (
                      <div className="ml-4 mt-2">
                        <p className="kicker mb-1.5 flex items-center gap-1">
                          <Lightbulb aria-hidden weight="fill" className="size-3 text-[var(--amber-600)]" />
                          {t("learningLabel")}
                        </p>
                        <ul className="flex flex-wrap gap-1.5">
                          {gap.learning.map((s, j) => (
                            <li key={j}>
                              <LearningChip suggestion={s} />
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        </Reveal>
      )}

      {report.per_question.length > 0 && (
        <Reveal>
          <section>
            <h3 className="mb-3 text-sm font-bold text-[var(--text-primary)]">
              {t("perQuestionTitle")}
            </h3>
            <ol className="space-y-3">
              {report.per_question.map((q, i) => (
                <li
                  key={i}
                  className="overflow-hidden rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)]"
                >
                  <div className="flex items-start gap-3 border-b border-[var(--border-default)] px-5 py-3.5">
                    <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-[var(--bg-muted)] text-xs font-bold tabular-nums text-[var(--text-primary)]">
                      {i + 1}
                    </span>
                    <p className="text-sm font-semibold leading-relaxed text-[var(--text-primary)]">
                      {q.question}
                    </p>
                  </div>
                  <div className="space-y-3 px-5 py-4">
                    {q.observation.trim() && (
                      <Row
                        icon={Notepad}
                        iconClass="text-[var(--text-secondary)]"
                        label={t("observationLabel")}
                        text={q.observation}
                      />
                    )}
                    {q.suggestion.trim() && (
                      <Row
                        icon={Lightbulb}
                        iconClass="text-[var(--amber-600)]"
                        label={t("suggestionLabel")}
                        text={q.suggestion}
                      />
                    )}
                  </div>
                </li>
              ))}
            </ol>
          </section>
        </Reveal>
      )}

      {printable && (
        <div
          data-mi-print-hide
          className="flex flex-wrap items-center gap-3 border-t border-[var(--border-default)] pt-5"
        >
          <Button variant="secondary" size="sm" onClick={handleDownloadPdf}>
            <FilePdf aria-hidden weight="bold" className="size-4" />
            {t("downloadPdf")}
          </Button>
          {jobId && (
            <Link href={`/jobs/${jobId}/interview`}>
              <Button variant="primary" size="sm">
                <ArrowClockwise aria-hidden weight="bold" className="size-4" />
                {t("practiceAgain")}
              </Button>
            </Link>
          )}
        </div>
      )}
    </div>
  );
}

function Row({
  icon: Icon,
  iconClass,
  label,
  text,
}: {
  icon: React.ElementType;
  iconClass: string;
  label: string;
  text: string;
}) {
  return (
    <div>
      <div className="mb-1 flex items-center gap-1.5">
        <Icon aria-hidden weight="duotone" className={cn("size-3.5 shrink-0", iconClass)} />
        <span className="kicker">{label}</span>
      </div>
      <p className="whitespace-pre-line text-sm leading-relaxed text-[var(--text-secondary)]">
        {text}
      </p>
    </div>
  );
}

/** Map a coarse learning-resource kind to a representative icon (defensive). */
function iconForKind(kind: string | null | undefined): React.ElementType {
  switch ((kind ?? "").toLowerCase()) {
    case "course":
    case "cert":
    case "certification":
      return GraduationCap;
    case "article":
    case "read":
    case "guide":
    case "doc":
      return Article;
    case "video":
    case "watch":
      return PlayCircle;
    case "practice":
    case "exercise":
    case "drill":
      return Barbell;
    default:
      return BookOpen;
  }
}

/** A neat learning-suggestion chip rendered under a gap. */
function LearningChip({ suggestion }: { suggestion: MockInterviewLearningSuggestion }) {
  const Icon = iconForKind(suggestion.kind);
  return (
    <span className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-[var(--border-default)] bg-[var(--bg-subtle)] px-2.5 py-1 text-[11px] font-medium text-[var(--text-secondary)]">
      <Icon aria-hidden weight="duotone" className="size-3 shrink-0 text-[var(--content-ai)]" />
      <span className="truncate" title={suggestion.title}>
        {suggestion.title}
      </span>
    </span>
  );
}

/** Gentle on-scroll reveal. Renders visible immediately under reduced motion. */
function Reveal({ children }: { children: React.ReactNode }) {
  const reduced = usePrefersReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    if (reduced) {
      setShown(true);
      return;
    }
    const node = ref.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      setShown(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setShown(true);
            io.disconnect();
            break;
          }
        }
      },
      { threshold: 0.12 },
    );
    io.observe(node);
    return () => io.disconnect();
  }, [reduced]);

  return (
    <div
      ref={ref}
      style={{
        opacity: shown ? 1 : 0,
        transform: shown ? "none" : "translateY(10px)",
        transition: reduced ? "none" : "opacity 450ms ease, transform 450ms ease",
      }}
    >
      {children}
    </div>
  );
}
