"use client";

import {
  Brain,
  CheckCircle,
  ClockCountdown,
  Robot,
  ShieldCheck,
  SpinnerGap,
  StopCircle,
  WarningCircle,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { apiFetch, apiMessage } from "@/lib/api/client";
import type { AIRun, AIRunType, AgentCapability } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { PanelSkeleton } from "@/components/ui/skeleton";

type TaskDraft = {
  primary: string;
  secondary: string;
  targetSkills: string;
};

const defaultDraft: TaskDraft = {
  primary: "",
  secondary: "",
  targetSkills: "",
};

export function AIOperations({ compact = false }: { compact?: boolean }) {
  const { dictionary } = useI18n();
  const [capabilities, setCapabilities] = useState<AgentCapability[]>([]);
  const [runs, setRuns] = useState<AIRun[]>([]);
  const [taskType, setTaskType] = useState<AIRunType>("career_coaching");
  const [draft, setDraft] = useState(defaultDraft);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);

  const labels: Record<AIRunType, string> = useMemo(
    () => ({
      career_coaching: dictionary.ai.careerCoaching,
      cv_extraction: dictionary.ai.cvExtraction,
      profile_matching: dictionary.ai.profileMatching,
      jd_analysis: dictionary.ai.jdAnalysis,
      moderation: dictionary.ai.moderation,
      admin_review: dictionary.ai.adminReview,
      verification: dictionary.ai.verification,
    }),
    [dictionary.ai],
  );

  const load = useCallback(async () => {
    try {
      const [agentData, runData] = await Promise.all([
        apiFetch<AgentCapability[]>("/ai/runs/capabilities"),
        apiFetch<AIRun[]>("/ai/runs/"),
      ]);
      setCapabilities(agentData);
      setRuns(runData);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setLoading(false);
    }
  }, [dictionary.common.retry]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    const active = runs.some((run) => ["QUEUED", "RUNNING"].includes(run.status));
    if (!active) return;
    const timer = window.setInterval(() => void load(), 1200);
    return () => window.clearInterval(timer);
  }, [runs, load]);

  function buildMetadata(): Record<string, unknown> {
    if (taskType === "career_coaching") {
      return {
        profile_text: draft.primary,
        target_skills: draft.targetSkills
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
      };
    }
    if (taskType === "cv_extraction") return { raw_text: draft.primary };
    if (taskType === "profile_matching") {
      return { cv_text: draft.primary, job_description: draft.secondary };
    }
    if (taskType === "jd_analysis") return { job_description: draft.primary };
    if (taskType === "moderation") return { content: draft.primary };
    if (taskType === "admin_review") {
      return {
        evidence: draft.primary.split("\n").filter(Boolean),
        risk_flags: draft.secondary.split(",").filter(Boolean),
      };
    }
    return {
      submission: { summary: draft.primary },
      required_fields: draft.secondary.split(",").filter(Boolean),
    };
  }

  async function createRun(event: React.FormEvent) {
    event.preventDefault();
    if (!draft.primary.trim()) return;
    setCreating(true);
    try {
      const run = await apiFetch<AIRun>("/ai/runs/", {
        method: "POST",
        body: JSON.stringify({
          run_type: taskType,
          run_metadata: buildMetadata(),
        }),
      });
      setRuns((current) => [run, ...current]);
      setDraft(defaultDraft);
      toast.success(dictionary.ai.running);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.ai.failed));
    } finally {
      setCreating(false);
    }
  }

  async function cancelRun(runId: string) {
    try {
      const run = await apiFetch<AIRun>(`/ai/runs/${runId}/cancel`, {
        method: "POST",
      });
      setRuns((current) =>
        current.map((item) => (item.run_id === runId ? run : item)),
      );
    } catch (error) {
      toast.error(apiMessage(error, dictionary.ai.failed));
    }
  }

  return (
    <div className={cn("grid gap-5", compact ? "p-4" : "lg:grid-cols-[380px_minmax(0,1fr)]")}>
      <div className="space-y-5">
        <form onSubmit={createRun} className="rounded-2xl border bg-white p-5">
          <div className="flex items-start gap-3">
            <div className="flex size-10 items-center justify-center rounded-xl bg-blue-50 text-primary">
              <Brain className="size-5" weight="duotone" />
            </div>
            <div>
              <h2 className="font-semibold">{dictionary.ai.newRun}</h2>
              <p className="mt-1 text-xs leading-5 text-muted">
                {dictionary.ai.privacyNotice}
              </p>
            </div>
          </div>
          <label className="mt-5 block text-sm font-semibold">
            {dictionary.ai.task}
          </label>
          <select
            value={taskType}
            onChange={(event) => setTaskType(event.target.value as AIRunType)}
            className="focus-ring mt-2 h-11 w-full rounded-xl border bg-white px-3 text-sm"
          >
            {capabilities.map((capability) => (
              <option key={capability.task_type} value={capability.task_type}>
                {labels[capability.task_type as AIRunType] || capability.task_type}
              </option>
            ))}
          </select>
          <label className="mt-4 block text-sm font-semibold">
            {dictionary.ai.input}
          </label>
          <textarea
            value={draft.primary}
            onChange={(event) =>
              setDraft((current) => ({ ...current, primary: event.target.value }))
            }
            placeholder={dictionary.ai.profilePlaceholder}
            className="focus-ring mt-2 min-h-32 w-full resize-y rounded-xl border bg-slate-50 p-3 text-sm leading-6"
            required
          />
          {taskType === "profile_matching" ||
          taskType === "admin_review" ||
          taskType === "verification" ? (
            <textarea
              value={draft.secondary}
              onChange={(event) =>
                setDraft((current) => ({ ...current, secondary: event.target.value }))
              }
              placeholder={
                taskType === "profile_matching"
                  ? dictionary.ai.jdAnalysis
                  : dictionary.forms.notes
              }
              className="focus-ring mt-3 min-h-24 w-full resize-y rounded-xl border p-3 text-sm"
            />
          ) : null}
          {taskType === "career_coaching" ? (
            <Input
              value={draft.targetSkills}
              onChange={(event) =>
                setDraft((current) => ({ ...current, targetSkills: event.target.value }))
              }
              placeholder={dictionary.ai.targetSkills}
              className="mt-3 rounded-xl"
            />
          ) : null}
          <Button
            type="submit"
            className="mt-4 w-full rounded-xl"
            disabled={creating || !draft.primary.trim()}
          >
            {creating ? (
              <SpinnerGap className="size-5 animate-spin" />
            ) : (
              <Robot className="size-5" weight="duotone" />
            )}
            {creating ? dictionary.ai.running : dictionary.ai.start}
          </Button>
        </form>

        {!compact ? (
          <div className="rounded-2xl border bg-white p-5">
            <h2 className="font-semibold">{dictionary.ai.capabilities}</h2>
            <div className="mt-4 space-y-3">
              {capabilities.map((capability) => (
                <div key={capability.task_type} className="rounded-xl bg-slate-50 p-3">
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="size-4 text-primary" weight="duotone" />
                    <p className="text-sm font-semibold">
                      {labels[capability.task_type as AIRunType] || capability.agent}
                    </p>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-muted">{capability.purpose}</p>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      <section className="rounded-2xl border bg-white">
        <div className="border-b p-5">
          <h2 className="font-semibold">{dictionary.ai.runHistory}</h2>
          <p className="mt-1 text-sm text-muted">{dictionary.ai.description}</p>
        </div>
        <div className="p-4 sm:p-5">
          {loading ? <PanelSkeleton /> : null}
          {!loading && !runs.length ? (
            <EmptyState
              icon={Robot}
              title={dictionary.ai.noRuns}
              description={dictionary.ai.noRunsDescription}
            />
          ) : null}
          {!loading && runs.length ? (
            <div className="space-y-3">
              {runs.slice(0, compact ? 6 : 30).map((run) => (
                <RunCard
                  key={run.run_id}
                  run={run}
                  label={labels[run.run_type as AIRunType] || run.run_type}
                  onCancel={() => cancelRun(run.run_id)}
                />
              ))}
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}

function RunCard({
  run,
  label,
  onCancel,
}: {
  run: AIRun;
  label: string;
  onCancel: () => void;
}) {
  const { locale, dictionary } = useI18n();
  const active = ["QUEUED", "RUNNING"].includes(run.status);
  const failed = run.status === "FAILED";
  const result = run.result as
    | {
        agent?: string;
        confidence?: number;
        requires_human_review?: boolean;
        output?: Record<string, unknown>;
        steps?: Array<{ action?: string; summary?: string }>;
      }
    | null;
  const Icon = active
    ? ClockCountdown
    : failed
      ? WarningCircle
      : run.status === "CANCELLED"
        ? StopCircle
        : CheckCircle;

  return (
    <article className="rounded-2xl border p-4 transition-colors hover:border-blue-200">
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "flex size-10 shrink-0 items-center justify-center rounded-xl",
            active
              ? "bg-amber-50 text-warning"
              : failed
                ? "bg-red-50 text-danger"
                : "bg-emerald-50 text-success",
          )}
        >
          <Icon className={cn("size-5", active && "animate-pulse")} weight="duotone" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-semibold">{label}</p>
            <Badge
              tone={
                active ? "amber" : failed ? "red" : run.status === "DONE" ? "green" : "gray"
              }
            >
              {run.status}
            </Badge>
            {result?.requires_human_review ? (
              <Badge tone="blue">{dictionary.ai.humanReview}</Badge>
            ) : null}
          </div>
          <p className="mt-1 text-xs text-muted">
            {new Intl.DateTimeFormat(locale, {
              dateStyle: "medium",
              timeStyle: "short",
            }).format(new Date(run.created_at))}
            {result?.agent ? ` · ${result.agent}` : ""}
          </p>
        </div>
        {active ? (
          <Button variant="ghost" size="sm" onClick={onCancel}>
            <StopCircle className="size-4" />
            {dictionary.common.cancel}
          </Button>
        ) : null}
      </div>
      {run.error ? (
        <p className="mt-3 rounded-xl bg-red-50 p-3 text-xs leading-5 text-red-700">
          {run.error}
        </p>
      ) : null}
      {result?.steps?.length ? (
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          {result.steps.slice(0, 6).map((step, index) => (
            <div key={`${step.action}-${index}`} className="rounded-xl bg-slate-50 p-3">
              <p className="text-xs font-semibold capitalize">
                {step.action?.replaceAll("_", " ")}
              </p>
              <p className="mt-1 text-xs leading-5 text-muted">{step.summary}</p>
            </div>
          ))}
        </div>
      ) : null}
      {result?.output ? (
        <details className="mt-3 rounded-xl border bg-slate-50">
          <summary className="focus-ring cursor-pointer list-none px-3 py-2 text-xs font-semibold text-primary">
            {dictionary.ai.result}
          </summary>
          <pre className="max-h-64 overflow-auto border-t p-3 text-[11px] leading-5 text-slate-600">
            {JSON.stringify(result.output, null, 2)}
          </pre>
        </details>
      ) : null}
    </article>
  );
}
