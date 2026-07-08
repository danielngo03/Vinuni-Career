"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowClockwise,
  Barbell,
  BookOpen,
  Certificate,
  CheckCircle,
  FileText,
  GraduationCap,
  Lightbulb,
  NotePencil,
  Sparkle,
  Star,
  Translate,
  WarningCircle,
  Wrench,
} from "@phosphor-icons/react";
import { Sheet, Button, Skeleton } from "@/components/ui";
import {
  cvApi,
  jobsApi,
  type FitAnalysis,
  type StudentLearningGap,
  type StudentLearningResource,
} from "@/lib/api";
import { fitTextColor, fitTier, rankByScore } from "@/lib/cv/fit";
import { drawerQueryEnabled } from "@/lib/jobs/job-intelligence";
import { AiEnergyHint } from "./ai-energy-hint";
import { ImprovementRow } from "./improvement-row";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onClose: () => void;
  jobId: string;
  /** Learning gaps carried from the already-loaded student-intelligence payload. */
  learningGaps: StudentLearningGap[];
  /** Recommended CV id from student-intelligence (the default CV to analyze). */
  bestCvId: string | null;
}

/**
 * Right-side "Analyze CV" drawer (WS-4). Opened on demand from the score-only
 * default panel; the metered `fit-explanation` model call fires ONLY when the
 * drawer is open (`enabled: drawerQueryEnabled(open)`) — never on job-detail
 * load. Shows the best CV to use, the structured matched/gap analysis, one-click
 * confirmation-gated improvements, and the learning gaps — all leak-safe.
 */
export function AnalyzeCvDrawer({
  open,
  onClose,
  jobId,
  learningGaps,
  bestCvId,
}: Props) {
  const t = useTranslations("jobs.studentIntel.analyze");
  const tf = useTranslations("cvFit");

  // Deterministic per-CV ranking (free) — the CV titles + picker + recommended.
  const fit = useQuery({
    queryKey: ["jobs", "cv-job-fit", jobId],
    queryFn: () => cvApi.jobFit(jobId),
    enabled: drawerQueryEnabled(open),
    staleTime: 60_000,
    retry: false,
  });

  const ranked = useMemo(
    () => (fit.data ? rankByScore(fit.data.results) : []),
    [fit.data],
  );
  const recommendedId = fit.data?.recommended_cv_id ?? bestCvId ?? ranked[0]?.cv_id ?? null;
  const [cvId, setCvId] = useState<string | null>(null);
  useEffect(() => {
    setCvId((prev) =>
      prev && ranked.some((r) => r.cv_id === prev) ? prev : recommendedId,
    );
  }, [ranked, recommendedId]);

  const selected = ranked.find((r) => r.cv_id === cvId) ?? null;

  // Metered AI analysis for the selected CV — fires ONLY while the drawer is open.
  const analysis = useQuery({
    queryKey: ["jobs", "fit-explanation", jobId, cvId],
    queryFn: () => jobsApi.fitExplanation(jobId, cvId),
    enabled: drawerQueryEnabled(open) && cvId != null,
    staleTime: 60_000,
    retry: false,
  });

  const hasCvs = fit.data ? fit.data.results.length > 0 : true;

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={t("title")}
      size="lg"
      overlayBlur={false}
      closeLabel={tf("aiAssessmentTitle")}
    >
      <div className="space-y-4">
        <p className="text-xs leading-relaxed text-[var(--text-muted)]">
          {t("subtitle")}
        </p>

        <AiEnergyHint />

        {fit.isPending ? (
          <AnalyzeSkeleton />
        ) : fit.isError ? (
          <ErrorBlock onRetry={() => void fit.refetch()} />
        ) : !hasCvs ? (
          <NoCvBlock />
        ) : (
          <>
            {/* Best CV to use + picker */}
            {selected && (
              <section>
                <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                  <FileText aria-hidden weight="duotone" className="size-3.5" />
                  {t("bestCvTitle")}
                </h3>
                <div className="flex items-center gap-3 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-3.5 py-3">
                  <span
                    className="flex size-11 shrink-0 items-center justify-center rounded-full text-sm font-extrabold tabular-nums"
                    style={{
                      color: fitTextColor(selected.score),
                      backgroundColor: "var(--bg-subtle)",
                    }}
                  >
                    {selected.score}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p
                      className="truncate text-sm font-bold text-[var(--text-primary)]"
                      title={selected.title}
                    >
                      {selected.title}
                    </p>
                    <span
                      className="text-[11px] font-semibold"
                      style={{ color: fitTextColor(selected.score) }}
                    >
                      {tf(`tier.${fitTier(selected.score)}`)}
                    </span>
                    {selected.cv_id === recommendedId && (
                      <span className="ml-1.5 inline-flex items-center gap-0.5 text-[11px] font-semibold text-[var(--teal-600)]">
                        <Star aria-hidden weight="fill" className="size-3" />
                        {tf("recommendedBadge")}
                      </span>
                    )}
                  </div>
                </div>

                {ranked.length > 1 && (
                  <div className="mt-2">
                    <p className="mb-1.5 text-[11px] font-medium text-[var(--text-muted)]">
                      {t("pickCvLabel")}
                    </p>
                    <ul role="listbox" aria-label={t("pickCvLabel")} className="space-y-1">
                      {ranked.map((r) => {
                        const isSel = r.cv_id === selected.cv_id;
                        return (
                          <li key={r.cv_id} role="option" aria-selected={isSel}>
                            <button
                              type="button"
                              onClick={() => setCvId(r.cv_id)}
                              aria-label={tf("cvScoreAria", { title: r.title, score: r.score })}
                              className={cn(
                                "flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30",
                                isSel
                                  ? "bg-[var(--surface-secondary)] ring-1 ring-inset ring-[var(--border-strong)]"
                                  : "hover:bg-[var(--surface-hover)]",
                              )}
                            >
                              <span
                                aria-hidden
                                className="flex size-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold tabular-nums"
                                style={{ color: fitTextColor(r.score), backgroundColor: "var(--bg-subtle)" }}
                              >
                                {r.score}
                              </span>
                              <span className="min-w-0 flex-1 truncate text-xs font-medium text-[var(--text-primary)]">
                                {r.title}
                              </span>
                              {r.cv_id === recommendedId && (
                                <Star aria-hidden weight="fill" className="size-3 shrink-0 text-[var(--teal-600)]" />
                              )}
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}
              </section>
            )}

            {/* AI structured analysis (on-demand, metered). */}
            <AnalysisSection
              pending={analysis.isPending || analysis.isFetching}
              analysis={analysis.data?.analysis ?? null}
              aiAvailable={analysis.data?.ai_explanation_available ?? false}
              explanation={analysis.data?.explanation ?? null}
            />

            {/* Confirmation-gated improvements (present even when AI narrative is off). */}
            {(analysis.data?.improvements?.length ?? 0) > 0 && (
              <section>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                  {t("improvementsTitle")}
                </h3>
                <div className="space-y-2">
                  {analysis.data!.improvements.map((h) => (
                    <ImprovementRow key={`imp-${h.cv_id}-${h.skill}`} handoff={h} />
                  ))}
                </div>
              </section>
            )}

            {/* Curated learning resources — advisory "what to study", DISTINCT
                from the confirmation-gated CV-Studio improvements above. */}
            <LearningResourcesSection
              resources={analysis.data?.learning_resources ?? []}
            />

            {/* Learning gaps + their CV-Studio hand-offs. */}
            {learningGaps.length > 0 && (
              <section>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                  {t("learningGapsTitle")}
                </h3>
                <div className="space-y-2">
                  {learningGaps.map((gap) => (
                    <div
                      key={gap.skill}
                      className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-3.5 py-3"
                    >
                      <p className="flex items-start gap-1.5 text-xs">
                        <Lightbulb aria-hidden weight="duotone" className="mt-0.5 size-3.5 shrink-0 text-[var(--amber-600)]" />
                        <span>
                          <span className="font-semibold text-[var(--text-primary)]">{gap.skill}</span>
                          <span className="mt-0.5 block leading-relaxed text-[var(--text-secondary)]">
                            {gap.suggestion}
                          </span>
                        </span>
                      </p>
                      {gap.cv_edit && (
                        <div className="mt-2">
                          <ImprovementRow handoff={gap.cv_edit} />
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            )}
          </>
        )}
      </div>
    </Sheet>
  );
}

function AnalysisSection({
  pending,
  analysis,
  aiAvailable,
  explanation,
}: {
  pending: boolean;
  analysis: FitAnalysis | null;
  aiAvailable: boolean;
  explanation: string | null;
}) {
  const t = useTranslations("jobs.studentIntel.analyze");

  if (pending) {
    return (
      <div role="status" aria-live="polite" className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3.5 py-3">
        <p className="flex items-center gap-2 text-xs font-semibold text-[var(--text-primary)]">
          <Sparkle aria-hidden weight="duotone" className="size-4 animate-pulse text-[var(--brand-primary)]" />
          {t("evaluating")}
        </p>
        <div className="mt-2 space-y-1.5" aria-hidden>
          <Skeleton className="h-2.5 w-full rounded" />
          <Skeleton className="h-2.5 w-5/6 rounded" />
          <Skeleton className="h-2.5 w-2/3 rounded" />
        </div>
      </div>
    );
  }

  // Deterministic content (improvements/learning gaps) still renders below even
  // when the AI narrative is unavailable — show an honest paused note, not an error.
  if (!aiAvailable || !analysis) {
    return (
      <p className="flex items-start gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3.5 py-2.5 text-xs leading-relaxed text-[var(--text-secondary)]">
        <WarningCircle aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0 text-[var(--text-muted)]" />
        {t("aiUnavailable")}
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {explanation && (
        <div className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3.5 py-3">
          <h3 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-[var(--text-primary)]">
            <Sparkle aria-hidden weight="duotone" className="size-4 text-[var(--brand-primary)]" />
            {t("overallTitle")}
          </h3>
          <p className="whitespace-pre-line text-xs leading-relaxed text-[var(--text-secondary)]">
            {explanation}
          </p>
        </div>
      )}

      {analysis.matched_evidence.length > 0 && (
        <section>
          <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-[var(--text-primary)]">
            <CheckCircle aria-hidden weight="duotone" className="size-4 text-[var(--teal-600)]" />
            {t("evidenceTitle")}
          </h3>
          <ul className="space-y-1.5">
            {analysis.matched_evidence.map((m, i) => (
              <li key={`ev-${i}`} className="rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-[var(--text-primary)]">{m.requirement}</span>
                  <span className="shrink-0 rounded-full bg-[var(--teal-50)] px-2 py-0.5 text-[10px] font-semibold text-[var(--teal-700)]">
                    {t(`evidenceStrength.${m.evidence_strength}`)}
                  </span>
                </div>
                <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-secondary)]">{m.reasoning}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {analysis.gaps.length > 0 && (
        <section>
          <h3 className="mb-2 text-xs font-semibold text-[var(--text-primary)]">{t("gapsTitle")}</h3>
          <ul className="space-y-1.5">
            {analysis.gaps.map((g, i) => (
              <li key={`gap-${i}`} className="rounded-lg border border-dashed border-[var(--amber-600)]/40 bg-[var(--amber-50)]/60 px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-[var(--text-primary)]">{g.requirement}</span>
                  <span className="shrink-0 rounded-full bg-[var(--amber-100)] px-2 py-0.5 text-[10px] font-semibold text-[var(--amber-700)]">
                    {t(`gapSeverity.${g.severity}`)}
                  </span>
                </div>
                <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-secondary)]">{g.suggestion}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

/** Coarse family a curated `resource_type` maps to (icon + type label). */
type ResourceKind =
  | "course"
  | "certification"
  | "practice"
  | "project"
  | "language"
  | "reflection";

const RESOURCE_KIND: Record<string, ResourceKind> = {
  foundations_course: "course",
  certification_path: "certification",
  hands_on_lab: "practice",
  coding_exercises: "practice",
  version_control_practice: "practice",
  guided_dataset: "practice",
  practice_project: "practice",
  build_api: "project",
  portfolio_piece: "project",
  language_practice: "language",
  experience_reflection: "reflection",
};

const KIND_ICON: Record<ResourceKind, React.ElementType> = {
  course: GraduationCap,
  certification: Certificate,
  practice: Barbell,
  project: Wrench,
  language: Translate,
  reflection: NotePencil,
};

function resourceKind(resourceType: string): ResourceKind {
  return RESOURCE_KIND[resourceType] ?? "practice";
}

/**
 * Curated learning resources for the fit gaps — advisory "what to study/practise"
 * reading. Deliberately SEPARATE from the confirmation-gated CV-Studio
 * `improvements` (those mutate the CV on accept; these do not). Renders nothing
 * when empty. Leak-safe: no URLs, no provider/model internals.
 */
function LearningResourcesSection({
  resources,
}: {
  resources: StudentLearningResource[];
}) {
  const t = useTranslations("jobs.studentIntel.analyze");
  if (resources.length === 0) return null;
  return (
    <section>
      <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        <BookOpen aria-hidden weight="duotone" className="size-3.5" />
        {t("learningResourcesTitle")}
      </h3>
      <ul className="space-y-2">
        {resources.map((r) => {
          const kind = resourceKind(r.resource_type);
          const Icon = KIND_ICON[kind];
          return (
            <li
              key={`lr-${r.skill}-${r.resource_type}`}
              className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-3.5 py-3"
            >
              <div className="flex items-start gap-2.5">
                <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md bg-[var(--bg-subtle)] text-[var(--text-secondary)]">
                  <Icon aria-hidden weight="duotone" className="size-3.5" />
                </span>
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-1.5">
                    <span className="text-xs font-semibold text-[var(--text-primary)]">
                      {r.skill}
                    </span>
                    <span className="rounded-full bg-[var(--bg-subtle)] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                      {t(`resourceKind.${kind}`)}
                    </span>
                  </p>
                  <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-secondary)]">
                    {r.suggestion}
                  </p>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function NoCvBlock() {
  const t = useTranslations("jobs.studentIntel");
  return (
    <div className="flex flex-col items-start gap-3 rounded-xl border border-[var(--border-default)] bg-[var(--surface-secondary)] px-4 py-5">
      <p className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
        <FileText aria-hidden weight="duotone" className="size-5 text-[var(--text-muted)]" />
        {t("fitNoCvTitle")}
      </p>
      <p className="text-sm text-[var(--text-secondary)]">{t("fitNoCvBody")}</p>
    </div>
  );
}

function ErrorBlock({ onRetry }: { onRetry: () => void }) {
  const t = useTranslations("jobs.studentIntel");
  return (
    <div role="alert" className="flex flex-col items-start gap-3 rounded-xl border border-[var(--border-default)] bg-[var(--surface-secondary)] px-4 py-4">
      <p className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
        <WarningCircle aria-hidden weight="duotone" className="size-5 text-[var(--brand-red)]" />
        {t("errorTitle")}
      </p>
      <p className="text-sm text-[var(--text-secondary)]">{t("errorBody")}</p>
      <Button variant="secondary" size="sm" onClick={onRetry}>
        <ArrowClockwise aria-hidden weight="bold" className="size-4" />
      </Button>
    </div>
  );
}

function AnalyzeSkeleton() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-16 w-full rounded-xl" />
      <Skeleton className="h-24 w-full rounded-xl" />
      <Skeleton className="h-20 w-full rounded-xl" />
    </div>
  );
}
