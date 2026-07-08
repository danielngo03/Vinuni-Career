"use client";

import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ChartLineUp,
  Fire,
  Info,
  Sparkle,
  Target,
} from "@phosphor-icons/react";
import { Sheet, Skeleton } from "@/components/ui";
import { jobsApi, type StudentCompetitionIntelligence } from "@/lib/api";
import {
  competitionRows,
  competitionTone,
  drawerQueryEnabled,
  hasCompetitionSignal,
  type CompetitionRow,
} from "@/lib/jobs/job-intelligence";
import { AiEnergyHint } from "./ai-energy-hint";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onClose: () => void;
  jobId: string;
  /** Deterministic bands from the already-loaded student-intelligence payload. */
  competition: StudentCompetitionIntelligence;
}

const TONE_BADGE: Record<"low" | "moderate" | "high", { cls: string; icon: typeof Fire }> = {
  low: { cls: "bg-[var(--teal-50)] text-[var(--teal-700)] border border-[var(--teal-100)]", icon: ChartLineUp },
  moderate: { cls: "bg-[var(--amber-50)] text-[var(--amber-700)] border border-[var(--amber-100)]", icon: ChartLineUp },
  high: { cls: "bg-[var(--red-50)] text-[var(--red-600)] border border-[var(--red-100)]", icon: Fire },
};

/**
 * Right-side "Competition" drawer (WS-4 / WS-5). The deterministic bands come
 * free from the already-loaded student-intelligence payload; only the AI
 * narrative is fetched on demand (metered) when the drawer opens. Renders
 * privacy-safe BANDS ONLY — never a raw applicant count, individual score, or
 * exact rank — and shows an honest "not enough data" state when the signal is
 * too thin, never a fabricated value.
 */
export function CompetitionDrawer({ open, onClose, jobId, competition }: Props) {
  const t = useTranslations("jobs.studentIntel");
  const tc = useTranslations("jobs.studentIntel.competition");

  const hasSignal = hasCompetitionSignal(competition);

  // Fire the metered narrative ONLY when the drawer is open AND there is a real
  // signal to explain — never on the default load, never for a low-signal pool.
  const narrative = useQuery({
    queryKey: ["jobs", "competition-explanation", jobId],
    queryFn: () => jobsApi.competitionExplanation(jobId),
    enabled: drawerQueryEnabled(open) && hasSignal,
    staleTime: 60_000,
    retry: false,
  });

  const rows = competitionRows(competition);
  const tone = competition.label ? competitionTone(competition.label) : "moderate";
  const badge = TONE_BADGE[tone];
  const BadgeIcon = badge.icon;

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={tc("title")}
      size="lg"
      overlayBlur={false}
      closeLabel={tc("title")}
    >
      <div className="space-y-5">
        <p className="text-xs leading-relaxed text-[var(--text-muted)]">{tc("subtitle")}</p>

        {!hasSignal ? (
          <div className="flex flex-col items-start gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--surface-secondary)] px-4 py-5">
            <p className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
              <Info aria-hidden weight="duotone" className="size-5 text-[var(--text-muted)]" />
              {tc("lowSignalTitle")}
            </p>
            <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{tc("lowSignalBody")}</p>
          </div>
        ) : (
          <>
            {/* Headline level + basis */}
            <div className="flex flex-wrap items-center gap-2">
              <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold", badge.cls)}>
                <BadgeIcon aria-hidden weight="duotone" className="size-3.5" />
                {t(`competitionLabel.${competition.label}`)}
              </span>
              {competition.basis && (
                <span className="inline-flex items-center gap-1 text-[11px] font-medium text-[var(--text-muted)]">
                  <Info aria-hidden weight="duotone" className="size-3.5" />
                  {tc(`basis.${competition.basis}`)}
                </span>
              )}
            </div>

            {/* Metered AI narrative — fired only when the drawer opens. */}
            <NarrativeSection
              pending={narrative.isPending || narrative.isFetching}
              available={narrative.data?.ai_explanation_available ?? false}
              explanation={narrative.data?.explanation ?? null}
            />

            {/* Bands dashboard (band values only, no counts). */}
            <section>
              <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                <Target aria-hidden weight="duotone" className="size-3.5" />
                {tc("bandsTitle")}
              </h3>
              <dl className="divide-y divide-[var(--border-default)] overflow-hidden rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)]">
                {rows.map((row) => (
                  <BandRow key={row.key} row={row} />
                ))}
              </dl>
            </section>

            {/* Deterministic guidance. */}
            {competition.guidance.length > 0 && (
              <section>
                <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                  {t("guidanceTitle")}
                </h3>
                <ul className="space-y-1">
                  {competition.guidance.map((line) => (
                    <li key={line} className="flex items-start gap-1.5 text-xs leading-relaxed text-[var(--text-secondary)]">
                      <span className="mt-1.5 size-1 shrink-0 rounded-full bg-[var(--text-muted)]" />
                      {line}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}

        <p className="text-[10px] leading-relaxed text-[var(--text-muted)]">{tc("disclaimer")}</p>
      </div>
    </Sheet>
  );
}

function BandRow({ row }: { row: CompetitionRow }) {
  const t = useTranslations("jobs.studentIntel");
  const tc = useTranslations("jobs.studentIntel.competition");

  const label = tc(`rows.${row.key}`);
  let value: string;
  switch (row.key) {
    case "applicants_per_seat":
      value = tc(`applicantsPerSeat.${row.value}`);
      break;
    case "strong_density":
      value = tc(`strongDensity.${row.value}`);
      break;
    case "standing_vs_strong":
      value = tc(`standingVsStrong.${row.value}`);
      break;
    case "applicant_quality":
      value = t(`applicantQuality.${row.value}`);
      break;
    case "deadline":
      value = t(`deadlineFreshness.${row.value}`);
      break;
    default:
      value = row.value;
  }

  return (
    <div className="flex items-center justify-between gap-3 px-3.5 py-2.5">
      <dt className="text-xs text-[var(--text-muted)]">{label}</dt>
      <dd>
        {/* Calm coarse chip — a bucket label, never a raw applicant number. */}
        <span className="inline-flex items-center rounded-full border border-[var(--border-default)] bg-[var(--bg-subtle)] px-2.5 py-0.5 text-[11px] font-semibold text-[var(--text-primary)]">
          {value}
        </span>
      </dd>
    </div>
  );
}

function NarrativeSection({
  pending,
  available,
  explanation,
}: {
  pending: boolean;
  available: boolean;
  explanation: string | null;
}) {
  const tc = useTranslations("jobs.studentIntel.competition");

  return (
    <div className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3.5 py-3">
      <h3 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-[var(--text-primary)]">
        <Sparkle aria-hidden weight="duotone" className="size-4 text-[var(--brand-primary)]" />
        {tc("narrativeTitle")}
      </h3>
      <AiEnergyHint className="mb-2.5" />
      {pending ? (
        <div role="status" aria-live="polite" className="space-y-1.5">
          <p className="text-[11px] text-[var(--text-muted)]">{tc("narrativeEvaluating")}</p>
          <Skeleton className="h-2.5 w-full rounded" />
          <Skeleton className="h-2.5 w-4/5 rounded" />
        </div>
      ) : available && explanation ? (
        <p className="whitespace-pre-line text-xs leading-relaxed text-[var(--text-secondary)]">
          {explanation}
        </p>
      ) : (
        <p className="text-[11px] leading-relaxed text-[var(--text-muted)]">{tc("narrativeUnavailable")}</p>
      )}
    </div>
  );
}
