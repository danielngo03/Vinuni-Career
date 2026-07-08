"use client";

import { useTranslations } from "next-intl";
import { CheckCircle, TestTube, WarningCircle } from "@phosphor-icons/react";
import { StatusBadge, type StatusTone } from "@/components/ui";
import type { DryRunResult, DryRunStep } from "@/lib/api";

const STEP_TONE: Record<DryRunStep["status"], StatusTone> = {
  success: "active",
  failed: "rejected",
  skipped: "pending",
};

/**
 * Renders a dry-run's node-by-node simulated trail, clearly marked as
 * simulated (never a real execution) — docs/PARTNER_RBAC_ANALYTICS_SPEC.md
 * "Show dry-run output using sample events with PII redacted".
 */
export function DryRunTrail({ result }: { result: DryRunResult }) {
  const t = useTranslations("workflowBuilder");

  return (
    <div className="space-y-3" data-testid="dry-run-trail">
      <div
        className="flex items-center gap-2 rounded-lg border border-[var(--teal-500)]/40 bg-[var(--teal-50)] px-3 py-2 text-xs font-semibold text-[var(--teal-700)]"
        data-testid="dry-run-simulated-badge"
      >
        <TestTube aria-hidden weight="fill" className="size-4 shrink-0" />
        {t("dryRunSimulatedBadge")}
      </div>
      <ol className="space-y-2">
        {result.steps.map((step, i) => (
          <li
            key={`${step.node_id}-${i}`}
            className="flex items-start gap-3 rounded-xl border border-[var(--border-subtle)] bg-white/90 px-3.5 py-2.5"
            data-testid={`dry-run-step-${step.node_id}`}
          >
            <span className="mt-0.5 shrink-0">
              {step.status === "success" && (
                <CheckCircle aria-hidden weight="fill" className="size-4 text-[var(--teal-600)]" />
              )}
              {step.status === "failed" && (
                <WarningCircle aria-hidden weight="fill" className="size-4 text-[var(--brand-red)]" />
              )}
              {step.status === "skipped" && (
                <WarningCircle aria-hidden weight="fill" className="size-4 text-[var(--amber-600)]" />
              )}
            </span>
            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-[var(--text-muted)]">{step.node_id}</span>
                <StatusBadge tone={STEP_TONE[step.status]}>
                  {t(`dryRunStepStatus.${step.status}`)}
                </StatusBadge>
              </div>
              {step.user_safe_error && (
                <p className="text-sm text-[var(--brand-red)]">{step.user_safe_error}</p>
              )}
              {Object.keys(step.output_summary).length > 0 && (
                <p className="truncate text-xs text-[var(--text-muted)]">
                  {Object.entries(step.output_summary)
                    .map(([k, v]) => `${k}: ${String(v)}`)
                    .join(" · ")}
                </p>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
