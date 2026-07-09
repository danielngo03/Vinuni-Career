"use client";

import type { ReactNode } from "react";
import { useTranslations } from "next-intl";
import { CheckCircle2, FlaskConical, MinusCircle, XCircle } from "lucide-react";
import { StatusChip, Timeline, type ActivityEntry, type ChipTone } from "@/components/kit";
import type { DryRunResult, DryRunStep } from "@/lib/api";

const STEP_META: Record<
  DryRunStep["status"],
  { icon: ActivityEntry["icon"]; tone: ChipTone }
> = {
  success: { icon: CheckCircle2, tone: "success" },
  failed: { icon: XCircle, tone: "danger" },
  skipped: { icon: MinusCircle, tone: "warning" },
};

/**
 * Renders a dry-run's node-by-node simulated trail on the v10 {@link Timeline},
 * clearly marked as simulated (never a real execution) —
 * docs/PARTNER_RBAC_ANALYTICS_SPEC.md "Show dry-run output using sample events
 * with PII redacted".
 */
export function DryRunTrail({ result }: { result: DryRunResult }) {
  const t = useTranslations("workflowBuilder");

  const items: ActivityEntry[] = result.steps.map((step, i) => {
    const meta = STEP_META[step.status];
    const summary =
      Object.keys(step.output_summary).length > 0
        ? Object.entries(step.output_summary)
            .map(([k, v]) => `${k}: ${String(v)}`)
            .join(" · ")
        : null;
    let metaNode: ReactNode;
    if (step.user_safe_error || summary) {
      metaNode = (
        <>
          {step.user_safe_error && (
            <span className="block" style={{ color: "var(--content-danger)" }}>
              {step.user_safe_error}
            </span>
          )}
          {summary && <span className="mt-0.5 block truncate">{summary}</span>}
        </>
      );
    }
    return {
      key: `${step.node_id}-${i}`,
      icon: meta.icon,
      tone: meta.tone,
      title: (
        <span
          className="flex flex-wrap items-center gap-2"
          data-testid={`dry-run-step-${step.node_id}`}
        >
          <span className="font-mono type-caption text-muted-foreground">{step.node_id}</span>
          <StatusChip tone={meta.tone} size="sm">
            {t(`dryRunStepStatus.${step.status}`)}
          </StatusChip>
        </span>
      ),
      meta: metaNode,
    };
  });

  return (
    <div className="space-y-4" data-testid="dry-run-trail">
      <div
        className="flex w-fit items-center gap-2 rounded-full px-3 py-1.5"
        style={{ background: "var(--content-info-soft)", color: "var(--content-info)" }}
        data-testid="dry-run-simulated-badge"
      >
        <FlaskConical aria-hidden className="size-4 shrink-0" strokeWidth={2} />
        <span className="type-caption font-semibold">{t("dryRunSimulatedBadge")}</span>
      </div>
      <Timeline items={items} />
    </div>
  );
}
