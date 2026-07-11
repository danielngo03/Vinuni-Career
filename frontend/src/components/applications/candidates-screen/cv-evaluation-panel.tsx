"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  CircleSlash,
  Loader2,
  MinusCircle,
  RefreshCw,
  ShieldQuestion,
  Sparkles,
  WifiOff,
} from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui";
import { StatusChip, type ChipTone } from "@/components/kit";
import { formatDateTimeShort } from "@/lib/format";
import { ApiError, applicationsApi } from "@/lib/api";
// `CvEvaluation` is exported via `export *` from the applications barrel; the
// top-level `@/lib/api` index uses an explicit allow-list that Lane 1 owns and
// does not yet re-export it (see handoff).
import type { CvEvaluation } from "@/lib/api/applications";

/* ---- recommendation → semantic tone (categorical-first, no 0–100 headline) -- */

function recommendationTone(rec: string): ChipTone {
  if (rec === "strong") return "success";
  if (rec === "consider") return "warning";
  if (rec === "weak") return "danger";
  return "neutral";
}

/* ---- per-criterion verdict → normalized bucket (Met / Partial / Not evidenced) */

type VerdictKind = "met" | "partial" | "not_evidenced" | "other";

function verdictKind(verdict: string): VerdictKind {
  const v = verdict.trim().toLowerCase();
  if (/(not|no\b|missing|none|absent|unclear|lack|without)/.test(v)) {
    return "not_evidenced";
  }
  if (/(met|meets|strong|yes|good|clear|pass|evidenced|solid)/.test(v)) {
    return "met";
  }
  if (/(partial|some|mixed|weak|maybe|partly|limited)/.test(v)) {
    return "partial";
  }
  return "other";
}

const VERDICT_TONE: Record<VerdictKind, ChipTone> = {
  met: "success",
  partial: "warning",
  not_evidenced: "neutral",
  other: "neutral",
};

const VERDICT_ICON: Record<VerdictKind, typeof CheckCircle2> = {
  met: CheckCircle2,
  partial: MinusCircle,
  not_evidenced: CircleSlash,
  other: MinusCircle,
};

/**
 * CvEvaluationPanel — the on-demand, recruiter-style AI read of a candidate's CV
 * against the job. It is CATEGORICAL-first: a recommendation chip + summary +
 * evidence-backed strengths + "not evidenced" gaps + per-criterion verdicts. It
 * never shows a competing 0–100 headline (the deterministic CV–JD match ring is
 * the number) and never exposes AI provider/model internals.
 *
 * The result is cached per application id (React Query, staleTime: Infinity) so
 * it survives prev/next navigation and drawer re-open; a Re-evaluate control
 * force-refreshes it. Quota/upgrade + AI-unavailable errors get persona-safe
 * states, never a raw error.
 */
export function CvEvaluationPanel({ applicationId }: { applicationId: string }) {
  const t = useTranslations("candidates");
  const forceRef = React.useRef(false);

  const q = useQuery<CvEvaluation, unknown>({
    queryKey: ["applications", "cvEvaluation", applicationId],
    queryFn: () =>
      applicationsApi.evaluateCv(
        applicationId,
        forceRef.current ? { force: true } : undefined,
      ),
    enabled: false,
    staleTime: Infinity,
    gcTime: 15 * 60_000,
    retry: false,
  });

  const run = React.useCallback(
    (force: boolean) => {
      forceRef.current = force;
      void q.refetch();
    },
    [q],
  );

  const data = q.data;
  const busy = q.isFetching;

  /* ------------------------------- loading -------------------------------- */
  if (!data && busy) {
    return (
      <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 px-6 py-10 text-center">
        <span
          className="inline-flex size-11 items-center justify-center rounded-full"
          style={{ background: "var(--content-ai-soft)" }}
        >
          <Loader2
            aria-hidden
            className="size-5 animate-spin"
            strokeWidth={2}
            style={{ color: "var(--content-ai)" }}
          />
        </span>
        <p className="type-small font-medium text-foreground">{t("evaluateLoading")}</p>
        <p className="type-caption text-muted-foreground">{t("evaluateLoadingHint")}</p>
      </div>
    );
  }

  /* -------------------------------- error --------------------------------- */
  if (!data && q.isError) {
    const err = q.error;
    const code = err instanceof ApiError ? err.code : undefined;

    if (code === "QUOTA_EXCEEDED" || code === "PAYMENT_REQUIRED") {
      return (
        <EvalState
          tone="warning"
          icon={ShieldQuestion}
          title={t("evaluateQuotaTitle")}
          body={t("evaluateQuotaBody")}
          action={
            <Link href="/partner/billing">
              <Button variant="secondary" size="sm">
                {t("evaluateQuotaCta")}
                <ArrowUpRight aria-hidden className="size-4" strokeWidth={1.8} />
              </Button>
            </Link>
          }
        />
      );
    }
    if (code === "AI_UNAVAILABLE") {
      return (
        <EvalState
          tone="neutral"
          icon={WifiOff}
          title={t("evaluateUnavailableTitle")}
          body={t("evaluateUnavailableBody")}
          action={
            <Button variant="secondary" size="sm" onClick={() => run(false)}>
              <RefreshCw aria-hidden className="size-4" strokeWidth={1.8} />
              {t("evaluateRetry")}
            </Button>
          }
        />
      );
    }
    return (
      <EvalState
        tone="danger"
        icon={AlertTriangle}
        title={t("evaluateErrorTitle")}
        body={t("evaluateErrorBody")}
        action={
          <Button variant="secondary" size="sm" onClick={() => run(false)}>
            <RefreshCw aria-hidden className="size-4" strokeWidth={1.8} />
            {t("evaluateRetry")}
          </Button>
        }
      />
    );
  }

  /* ------------------------- empty / not-yet-run -------------------------- */
  if (!data) {
    return (
      <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 px-6 py-10 text-center">
        <span
          className="inline-flex size-11 items-center justify-center rounded-full"
          style={{ background: "var(--content-ai-soft)" }}
        >
          <Sparkles
            aria-hidden
            className="size-5"
            strokeWidth={1.8}
            style={{ color: "var(--content-ai)" }}
          />
        </span>
        <div className="max-w-[26rem] space-y-1.5">
          <p className="type-body font-semibold text-foreground">{t("evaluateTitle")}</p>
          <p className="type-small text-muted-foreground">{t("evaluateIntro")}</p>
        </div>
        <Button variant="primary" size="sm" className="mt-1" onClick={() => run(false)}>
          <Sparkles aria-hidden className="size-4" strokeWidth={1.8} />
          {t("evaluateRun")}
        </Button>
        <p className="type-caption text-muted-foreground">{t("evaluateDisclaimer")}</p>
      </div>
    );
  }

  /* -------------------------------- result -------------------------------- */
  return (
    <div className="space-y-0">
      {/* Verdict header — recommendation chip is the headline (no 0–100 number). */}
      <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <StatusChip tone={recommendationTone(data.recommendation)}>
              {t.has(`evaluateRec_${data.recommendation}`)
                ? t(`evaluateRec_${data.recommendation}`)
                : data.recommendation}
            </StatusChip>
            {data.is_fallback && (
              <StatusChip tone="neutral" size="sm">
                <WifiOff aria-hidden className="size-3" strokeWidth={2} />
                {t("evaluateFallbackNote")}
              </StatusChip>
            )}
            <span className="type-caption text-muted-foreground">
              {data.evaluated_at
                ? t("evaluateMetaAt", { at: formatDateTimeShort(data.evaluated_at) })
                : t("evaluateMeta")}
            </span>
          </div>
          {data.summary && (
            <p className="type-small text-foreground">{data.summary}</p>
          )}
        </div>
        <Button
          variant="ghost"
          size="sm"
          loading={busy}
          onClick={() => run(true)}
          className="shrink-0"
        >
          <RefreshCw aria-hidden className="size-4" strokeWidth={1.8} />
          {t("evaluateRerun")}
        </Button>
      </div>

      {/* Strengths — each with concrete CV evidence. */}
      {data.strengths.length > 0 && (
        <EvalSection title={t("evaluateStrengthsTitle")}>
          <ul className="space-y-2.5">
            {data.strengths.map((s, i) => (
              <li key={i} className="flex items-start gap-2">
                <CheckCircle2
                  aria-hidden
                  className="mt-0.5 size-4 shrink-0"
                  strokeWidth={1.9}
                  style={{ color: "var(--content-success)" }}
                />
                <div className="min-w-0">
                  <p className="type-small font-medium text-foreground">{s.point}</p>
                  {s.evidence && (
                    <p className="mt-0.5 type-caption text-muted-foreground">
                      <span className="font-medium">{t("evaluateEvidenceLabel")}: </span>
                      {s.evidence}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </EvalSection>
      )}

      {/* Gaps — phrased as "not evidenced", with why it matters for the role. */}
      {data.gaps.length > 0 && (
        <EvalSection title={t("evaluateGapsTitle")}>
          <ul className="space-y-2.5">
            {data.gaps.map((g, i) => (
              <li key={i} className="flex items-start gap-2">
                <CircleSlash
                  aria-hidden
                  className="mt-0.5 size-4 shrink-0"
                  strokeWidth={1.9}
                  style={{ color: "var(--content-warning)" }}
                />
                <div className="min-w-0">
                  <p className="type-small font-medium text-foreground">{g.point}</p>
                  {g.why_it_matters && (
                    <p className="mt-0.5 type-caption text-muted-foreground">
                      <span className="font-medium">{t("evaluateWhyLabel")}: </span>
                      {g.why_it_matters}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </EvalSection>
      )}

      {/* Per-criterion verdicts. */}
      {data.criteria.length > 0 && (
        <EvalSection title={t("evaluateCriteriaTitle")}>
          <ul className="divide-y divide-border">
            {data.criteria.map((c, i) => {
              const kind = verdictKind(c.verdict);
              const Icon = VERDICT_ICON[kind];
              const label =
                kind === "other"
                  ? c.verdict
                  : t(`evaluateVerdict_${kind}`);
              return (
                <li key={i} className="flex items-start justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                  <div className="min-w-0">
                    <p className="type-small font-medium text-foreground">{c.name}</p>
                    {c.note && (
                      <p className="mt-0.5 type-caption text-muted-foreground">{c.note}</p>
                    )}
                  </div>
                  <StatusChip tone={VERDICT_TONE[kind]} size="sm" className="shrink-0">
                    <Icon aria-hidden className="size-3" strokeWidth={2} />
                    {label}
                  </StatusChip>
                </li>
              );
            })}
          </ul>
        </EvalSection>
      )}

      {/* Advisory disclaimer — AI output is a guide, never auto-decisive. */}
      <p className="flex items-start gap-1.5 px-5 py-3 type-caption text-muted-foreground">
        <Sparkles aria-hidden className="mt-0.5 size-3.5 shrink-0" strokeWidth={1.8} />
        {t("evaluateDisclaimer")}
      </p>
    </div>
  );
}

function EvalSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-b border-border px-5 py-4 last:border-b-0">
      <h4 className="mb-2.5 text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
        {title}
      </h4>
      {children}
    </section>
  );
}

function EvalState({
  tone,
  icon: Icon,
  title,
  body,
  action,
}: {
  tone: ChipTone;
  icon: typeof AlertTriangle;
  title: string;
  body: string;
  action?: React.ReactNode;
}) {
  const soft: Record<string, string> = {
    warning: "var(--content-warning-soft)",
    danger: "var(--content-danger-soft)",
    neutral: "var(--bg-muted)",
  };
  const fg: Record<string, string> = {
    warning: "var(--content-warning)",
    danger: "var(--content-danger)",
    neutral: "var(--text-muted)",
  };
  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 px-6 py-10 text-center">
      <span
        className="inline-flex size-11 items-center justify-center rounded-full"
        style={{ background: soft[tone] ?? "var(--bg-muted)" }}
      >
        <Icon
          aria-hidden
          className="size-5"
          strokeWidth={1.8}
          style={{ color: fg[tone] ?? "var(--text-muted)" }}
        />
      </span>
      <div className="max-w-[26rem] space-y-1.5">
        <p className="type-body font-semibold text-foreground">{title}</p>
        <p className="type-small text-muted-foreground">{body}</p>
      </div>
      {action}
    </div>
  );
}
