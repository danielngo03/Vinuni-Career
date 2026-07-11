"use client";

import { useTranslations } from "next-intl";
import { CheckCircle, Steps } from "@phosphor-icons/react";
import {
  deriveRoundPlan,
  type MockInterviewRound,
  type RoundPlan,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Tasteful multi-round / phase indicator for the mock-interview flow. All three
 * exports degrade to `null` when no usable rounds are present (defensive against
 * the optional backend contract), so callers can render them unconditionally.
 *
 * - {@link RoundPill}    — a compact "Round 2/3 · Technical" chip for the live
 *   room header.
 * - {@link RoundStepper} — a segmented progress bar + phase legend for the
 *   setup hero (`variant="hero"`, white-on-blue) and the coaching report
 *   (`variant="card"`).
 */

function bestLabel(round: MockInterviewRound): string {
  const persona = round.persona_label?.trim();
  return persona || round.label.trim();
}

/* --------------------------------- pill ---------------------------------- */

export function RoundPill({
  rounds,
  current,
  className,
}: {
  rounds: MockInterviewRound[] | null | undefined;
  current?: string | number | null;
  className?: string;
}) {
  const t = useTranslations("jobs.mockInterview");
  const plan = deriveRoundPlan(rounds, current);
  if (!plan) return null;

  const active = plan.rounds[plan.activeIndex];
  if (!active) return null;
  const label = bestLabel(active);

  return (
    <span
      className={cn(
        "inline-flex min-w-0 items-center gap-1.5 rounded-full border border-[var(--border-default)] bg-[var(--surface-card)] py-0.5 pl-1.5 pr-2.5",
        className,
      )}
    >
      <span
        aria-hidden
        className="flex size-4 shrink-0 items-center justify-center rounded-full"
        style={{ background: "var(--viz-indigo-soft)" }}
      >
        <Steps weight="bold" className="size-2.5" style={{ color: "var(--viz-indigo)" }} />
      </span>
      <span className="shrink-0 text-[11px] font-semibold tabular-nums text-[var(--text-secondary)]">
        {t("roundLabel", { n: plan.activeIndex + 1, total: plan.total })}
      </span>
      <span aria-hidden className="text-[11px] text-[var(--border-strong)]">
        ·
      </span>
      <span className="truncate text-[11px] font-medium text-[var(--text-muted)]" title={label}>
        {label}
      </span>
    </span>
  );
}

/* -------------------------------- stepper -------------------------------- */

type StepperVariant = "card" | "hero";

export function RoundStepper({
  rounds,
  current,
  variant = "card",
  className,
}: {
  rounds: MockInterviewRound[] | null | undefined;
  current?: string | number | null;
  variant?: StepperVariant;
  className?: string;
}) {
  const t = useTranslations("jobs.mockInterview");
  const plan = deriveRoundPlan(rounds, current);
  if (!plan) return null;

  const onHero = variant === "hero";

  return (
    <div className={cn("min-w-0", className)}>
      <div className="flex items-center justify-between gap-2">
        <p
          className={cn(
            "kicker",
            onHero && "text-white/70",
          )}
        >
          {t("roundPlanTitle")}
        </p>
        <span
          className={cn(
            "shrink-0 text-[11px] font-semibold tabular-nums",
            onHero ? "text-white/80" : "text-[var(--text-muted)]",
          )}
        >
          {t("roundLabel", { n: plan.activeIndex + 1, total: plan.total })}
        </span>
      </div>

      {/* segmented progress bar */}
      <div
        className="mt-2 flex items-center gap-1"
        role="img"
        aria-label={t("roundLabel", { n: plan.activeIndex + 1, total: plan.total })}
      >
        {plan.rounds.map((r, i) => (
          <SegmentBar key={r.id} plan={plan} index={i} onHero={onHero} />
        ))}
      </div>

      {/* phase legend */}
      <ul className="mt-3 flex flex-wrap gap-1.5">
        {plan.rounds.map((r, i) => (
          <PhaseChip key={r.id} round={r} plan={plan} index={i} onHero={onHero} />
        ))}
      </ul>
    </div>
  );
}

function segmentState(plan: RoundPlan, index: number): MockInterviewRound["status"] {
  const explicit = plan.rounds[index]?.status;
  if (explicit === "done" || explicit === "active" || explicit === "upcoming") {
    return explicit;
  }
  if (index < plan.activeIndex) return "done";
  if (index === plan.activeIndex) return "active";
  return "upcoming";
}

function SegmentBar({
  plan,
  index,
  onHero,
}: {
  plan: RoundPlan;
  index: number;
  onHero: boolean;
}) {
  const state = segmentState(plan, index);
  const fill = onHero
    ? state === "upcoming"
      ? "rgba(255,255,255,0.25)"
      : "rgba(255,255,255,0.9)"
    : state === "done"
      ? "var(--viz-indigo)"
      : state === "active"
        ? "var(--viz-indigo)"
        : "var(--bg-muted)";
  return (
    <span
      aria-hidden
      className={cn(
        "h-1.5 flex-1 rounded-full transition-colors duration-300",
        state === "active" && !onHero && "ring-2 ring-[var(--viz-indigo-soft)]",
      )}
      style={{ background: fill }}
    />
  );
}

function PhaseChip({
  round,
  plan,
  index,
  onHero,
}: {
  round: MockInterviewRound;
  plan: RoundPlan;
  index: number;
  onHero: boolean;
}) {
  const state = segmentState(plan, index);
  const label = bestLabel(round);

  const cls = onHero
    ? state === "active"
      ? "bg-white/20 text-white font-semibold"
      : state === "done"
        ? "bg-white/10 text-white/90"
        : "bg-white/5 text-white/60"
    : state === "active"
      ? "border border-[var(--viz-indigo)]/40 bg-[var(--viz-indigo-soft)] text-[var(--text-primary)] font-semibold"
      : state === "done"
        ? "border border-[var(--teal-500)]/35 bg-[var(--teal-50)] text-[var(--teal-700)]"
        : "border border-[var(--border-default)] bg-[var(--surface-card)] text-[var(--text-muted)]";

  return (
    <li
      className={cn(
        "inline-flex max-w-full items-center gap-1 rounded-full px-2.5 py-1 text-[11px]",
        cls,
      )}
    >
      {state === "done" ? (
        <CheckCircle
          aria-hidden
          weight="fill"
          className={cn("size-3 shrink-0", onHero ? "text-white/80" : "text-[var(--teal-600)]")}
        />
      ) : (
        <span
          aria-hidden
          className={cn(
            "size-1.5 shrink-0 rounded-full",
            state === "active"
              ? onHero
                ? "bg-white"
                : "bg-[var(--viz-indigo)]"
              : onHero
                ? "bg-white/40"
                : "bg-[var(--border-strong)]",
          )}
        />
      )}
      <span className="truncate" title={label}>
        {label}
      </span>
    </li>
  );
}
