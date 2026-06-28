"use client";

import {
  Buildings,
  CheckCircle,
  FlowArrow,
  Play,
  Robot,
  ShieldCheck,
  SpinnerGap,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { apiFetch, apiMessage } from "@/lib/api/client";
import type {
  AIUsageLog,
  RegistrationQueueItem,
  UniversityDashboard,
  VerificationPolicy,
  Workflow,
  WorkflowExecution,
} from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { Progress } from "@/components/ui/progress";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/dashboard/status-badge";

export function RegistrationCenter() {
  const { dictionary } = useI18n();
  const [items, setItems] = useState<RegistrationQueueItem[]>([]);
  const [policies, setPolicies] = useState<VerificationPolicy[]>([]);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [workingId, setWorkingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [queue, studentPolicy, partnerPolicy] = await Promise.all([
        apiFetch<RegistrationQueueItem[]>("/registrations/review-queue"),
        apiFetch<VerificationPolicy>(
          "/registrations/verification-policy/STUDENT",
        ),
        apiFetch<VerificationPolicy>(
          "/registrations/verification-policy/PARTNER",
        ),
      ]);
      setItems(queue);
      setPolicies([studentPolicy, partnerPolicy]);
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

  async function decide(
    item: RegistrationQueueItem,
    decision: "START_REVIEW" | "REQUEST_CHANGES" | "APPROVE" | "REJECT",
  ) {
    const note = notes[item.id]?.trim() || "";
    if (["REQUEST_CHANGES", "REJECT"].includes(decision) && !note) {
      toast.error(dictionary.forms.notes);
      return;
    }
    setWorkingId(item.id);
    try {
      await apiFetch(`/registrations/${item.id}/review`, {
        method: "POST",
        body: JSON.stringify({
          decision,
          note: note || undefined,
          checklist:
            decision === "REQUEST_CHANGES"
              ? [
                  {
                    code: `review-${item.version}`,
                    label: note,
                    resolved: false,
                  },
                ]
              : [],
        }),
      });
      await load();
      toast.success(dictionary.common.updated);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setWorkingId(null);
    }
  }

  async function updatePolicy(policy: VerificationPolicy, enabled: boolean) {
    try {
      await apiFetch(
        `/registrations/verification-policy/${policy.registration_type}`,
        {
          method: "PUT",
          body: JSON.stringify({
            mode: enabled ? "SHADOW" : "DISABLED",
            global_kill_switch: !enabled,
            confidence_threshold: policy.confidence_threshold,
            required_providers: policy.required_providers,
            required_documents: policy.required_documents,
            sample_rate: policy.sample_rate,
            model_version: policy.model_version,
          }),
        },
      );
      await load();
      toast.success(dictionary.common.updated);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    }
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
      <section className="rounded-2xl border bg-white">
        <div className="border-b p-5">
          <h2 className="font-semibold">{dictionary.sections.registrations}</h2>
          <p className="mt-1 text-sm text-muted">
            {dictionary.operations.university.registrationsDescription}
          </p>
        </div>
        <div className="p-4 sm:p-5">
          {loading ? <PanelSkeleton /> : null}
          {!loading && !items.length ? (
            <EmptyState
              icon={ShieldCheck}
              title={dictionary.common.empty}
              description={dictionary.operations.university.registrationsDescription}
            />
          ) : null}
          <div className="space-y-4">
            {items.map((item) => {
              const terminal = ["APPROVED", "REJECTED", "WITHDRAWN"].includes(
                item.status,
              );
              return (
                <article key={item.id} className="rounded-2xl border p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-semibold">{item.applicant_name}</h3>
                    <Badge tone={item.registration_type === "STUDENT" ? "blue" : "cyan"}>
                      {item.registration_type}
                    </Badge>
                    <StatusBadge status={item.status} />
                    <span className="text-xs text-muted">v{item.version}</span>
                  </div>
                  <p className="mt-1 text-sm text-muted">{item.applicant_email}</p>
                  <div className="mt-4 grid gap-2 sm:grid-cols-3">
                    {item.evidence.slice(0, 3).map((evidence) => (
                      <div key={evidence.id} className="rounded-xl bg-slate-50 p-3">
                        <p className="truncate text-xs font-semibold">
                          {evidence.provider.replaceAll("_", " ")}
                        </p>
                        <div className="mt-2 flex justify-between text-xs">
                          <span className="text-muted">{evidence.field_name}</span>
                          <span
                            className={
                              evidence.confidence >= 80
                                ? "font-semibold text-success"
                                : "font-semibold text-warning"
                            }
                          >
                            {evidence.confidence}%
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 rounded-xl border border-blue-100 bg-blue-50/60 p-3">
                    <div className="flex items-center gap-2 text-sm font-semibold">
                      <Robot className="size-4 text-primary" weight="duotone" />
                      {item.assessment.outcome || "MANUAL_REVIEW"} ·{" "}
                      {item.assessment.confidence || 0}%
                    </div>
                    <p className="mt-2 text-xs leading-5 text-muted">
                      {item.assessment.reasons?.join(" ") || dictionary.ai.advisory}
                    </p>
                  </div>
                  <div className="mt-4 grid gap-2 lg:grid-cols-[minmax(0,1fr)_auto]">
                    <Input
                      value={notes[item.id] || ""}
                      onChange={(event) =>
                        setNotes((current) => ({
                          ...current,
                          [item.id]: event.target.value,
                        }))
                      }
                      placeholder={dictionary.forms.notes}
                      disabled={terminal}
                    />
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={terminal || workingId === item.id}
                        onClick={() => decide(item, "REQUEST_CHANGES")}
                      >
                        <WarningCircle className="size-4" />
                        Request changes
                      </Button>
                      <Button
                        variant="danger"
                        size="sm"
                        disabled={terminal || workingId === item.id}
                        onClick={() => decide(item, "REJECT")}
                      >
                        <XCircle className="size-4" />
                      </Button>
                      <Button
                        size="sm"
                        disabled={terminal || workingId === item.id}
                        onClick={() => decide(item, "APPROVE")}
                      >
                        {workingId === item.id ? (
                          <SpinnerGap className="size-4 animate-spin" />
                        ) : (
                          <CheckCircle className="size-4" />
                        )}
                        Approve
                      </Button>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      </section>
      <aside className="space-y-4">
        {policies.map((policy) => (
          <article key={policy.id} className="rounded-2xl border bg-white p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-wide text-primary">
                  {policy.registration_type}
                </p>
                <h3 className="mt-1 font-semibold">{policy.mode}</h3>
              </div>
              <button
                type="button"
                onClick={() => updatePolicy(policy, policy.mode === "DISABLED")}
                className={`focus-ring relative h-7 w-12 cursor-pointer rounded-full transition-colors ${
                  policy.mode === "DISABLED" ? "bg-slate-200" : "bg-primary"
                }`}
                aria-label={dictionary.common.save}
              >
                <span
                  className={`absolute top-1 size-5 rounded-full bg-white shadow transition-transform ${
                    policy.mode === "DISABLED"
                      ? "translate-x-1"
                      : "translate-x-6"
                  }`}
                />
              </button>
            </div>
            <div className="mt-5">
              <div className="mb-2 flex justify-between text-xs">
                <span className="text-muted">Confidence</span>
                <span className="font-semibold">{policy.confidence_threshold}%</span>
              </div>
              <Progress value={policy.confidence_threshold} />
            </div>
            <p className="mt-4 text-xs leading-5 text-muted">
              {policy.model_version} · sample {policy.sample_rate}%
            </p>
          </article>
        ))}
      </aside>
    </div>
  );
}

export function ModerationCenter() {
  const { dictionary } = useI18n();
  const [data, setData] = useState<UniversityDashboard | null>(null);
  const [workingId, setWorkingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setData(await apiFetch<UniversityDashboard>("/dashboard/university"));
  }, []);
  useEffect(() => {
    const timer = window.setTimeout(() => load().catch(() => undefined), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function moderate(id: string, approve: boolean) {
    setWorkingId(id);
    try {
      await apiFetch(`/jobs/${id}/moderate`, {
        method: "POST",
        body: JSON.stringify({
          approve,
          reason: approve
            ? "Approved after governance review."
            : "Rejected after governance review.",
        }),
      });
      await load();
      toast.success(dictionary.common.updated);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setWorkingId(null);
    }
  }

  if (!data) return <PanelSkeleton />;
  return (
    <section className="rounded-2xl border bg-white p-4 sm:p-5">
      {!data.moderation_queue.length ? (
        <EmptyState
          icon={ShieldCheck}
          title={dictionary.common.empty}
          description={dictionary.operations.university.moderationDescription}
        />
      ) : (
        <div className="space-y-3">
          {data.moderation_queue.map((job) => (
            <article key={job.id} className="rounded-2xl border p-4">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-center">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-semibold">{job.title}</h3>
                    <StatusBadge status={job.status} />
                  </div>
                  <p className="mt-2 text-sm text-muted">{job.company}</p>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {(job.tags || []).map((tag) => (
                      <Badge key={tag} tone="gray">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => moderate(job.id, false)}
                    disabled={workingId === job.id}
                  >
                    <XCircle className="size-4" />
                    Reject
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => moderate(job.id, true)}
                    disabled={workingId === job.id}
                  >
                    <CheckCircle className="size-4" />
                    Approve
                  </Button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

export function PartnerDirectory() {
  const { dictionary } = useI18n();
  const [data, setData] = useState<UniversityDashboard | null>(null);
  const load = useCallback(
    () => apiFetch<UniversityDashboard>("/dashboard/university").then(setData),
    [],
  );
  useEffect(() => {
    const timer = window.setTimeout(() => load().catch(() => undefined), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function verify(id: string, current: boolean) {
    try {
      await apiFetch(`/organizations/${id}/verification`, {
        method: "PUT",
        body: JSON.stringify({ is_verified: !current }),
      });
      await load();
      toast.success(dictionary.common.updated);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    }
  }
  if (!data) return <PanelSkeleton />;
  return (
    <section className="rounded-2xl border bg-white p-4 sm:p-5">
      <div className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
        {data.partners.map((partner) => (
          <article key={partner.id} className="rounded-2xl border p-4">
            <div className="flex items-start gap-3">
              <div className="flex size-11 items-center justify-center rounded-xl bg-blue-50 text-primary">
                <Buildings className="size-5" weight="duotone" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-semibold">{partner.name}</p>
                <Badge
                  className="mt-2"
                  tone={partner.is_verified_partner ? "green" : "amber"}
                >
                  {partner.is_verified_partner ? "Verified" : "Pending"}
                </Badge>
              </div>
            </div>
            <Button
              className="mt-4 w-full"
              size="sm"
              variant={partner.is_verified_partner ? "outline" : "default"}
              onClick={() => verify(partner.id, partner.is_verified_partner)}
            >
              {partner.is_verified_partner ? dictionary.common.cancel : dictionary.common.save}
            </Button>
          </article>
        ))}
      </div>
    </section>
  );
}

export function WorkflowCenter() {
  const { dictionary } = useI18n();
  const [items, setItems] = useState<Workflow[]>([]);
  const [open, setOpen] = useState(false);
  const [execution, setExecution] = useState<WorkflowExecution | null>(null);

  const load = useCallback(async () => {
    setItems(await apiFetch<Workflow[]>("/workflows"));
  }, []);
  useEffect(() => {
    const timer = window.setTimeout(() => load().catch(() => undefined), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await apiFetch("/workflows", {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          trigger_event: form.get("trigger"),
          graph_data: {
            nodes: [
              { id: "trigger", type: "trigger" },
              { id: "notify", type: "notification" },
            ],
            edges: [{ source: "trigger", target: "notify" }],
          },
          is_active: true,
        }),
      });
      await load();
      setOpen(false);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    }
  }

  async function execute(id: string) {
    try {
      setExecution(
        await apiFetch<WorkflowExecution>(`/workflows/${id}/execute`, {
          method: "POST",
          body: JSON.stringify({ context: { source: "university-ui" } }),
        }),
      );
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    }
  }

  return (
    <>
      <section className="rounded-2xl border bg-white">
        <div className="flex items-center border-b p-5">
          <div>
            <h2 className="font-semibold">{dictionary.sections.workflows}</h2>
            <p className="mt-1 text-sm text-muted">
              {dictionary.operations.university.workflowsDescription}
            </p>
          </div>
          <Button className="ml-auto" onClick={() => setOpen(true)}>
            <FlowArrow className="size-4" />
            {dictionary.common.create}
          </Button>
        </div>
        <div className="grid gap-3 p-4 sm:p-5 lg:grid-cols-2">
          {items.map((workflow) => (
            <article key={workflow.id} className="rounded-2xl border p-4">
              <div className="flex items-center gap-3">
                <div className="flex size-10 items-center justify-center rounded-xl bg-blue-50 text-primary">
                  <FlowArrow className="size-5" weight="duotone" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold">{workflow.name}</p>
                  <p className="mt-1 text-xs text-muted">{workflow.trigger_event}</p>
                </div>
                <Badge tone={workflow.is_active ? "green" : "gray"}>
                  {workflow.is_active ? "Active" : "Disabled"}
                </Badge>
              </div>
              <div className="mt-4 rounded-xl bg-slate-50 p-3 text-xs text-muted">
                {graphCount(workflow.graph_data, "nodes")} nodes ·{" "}
                {graphCount(workflow.graph_data, "edges")} edges
              </div>
              <Button
                className="mt-4 w-full"
                size="sm"
                variant="outline"
                onClick={() => execute(workflow.id)}
              >
                <Play className="size-4" />
                Execute
              </Button>
            </article>
          ))}
          {!items.length ? (
            <EmptyState
              icon={FlowArrow}
              title={dictionary.common.empty}
              description={dictionary.operations.university.workflowsDescription}
              action={dictionary.common.create}
              onAction={() => setOpen(true)}
            />
          ) : null}
        </div>
        {execution ? (
          <div className="border-t p-5">
            <Badge tone="green">{execution.status}</Badge>
            <pre className="mt-3 overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-200">
              {JSON.stringify(execution.execution_trace, null, 2)}
            </pre>
          </div>
        ) : null}
      </section>
      <Modal
        open={open}
        onOpenChange={setOpen}
        title={dictionary.sections.workflows}
        description={dictionary.operations.university.workflowsDescription}
      >
        <form onSubmit={create} className="space-y-4">
          <Input name="name" required minLength={3} placeholder={dictionary.forms.title} />
          <Input
            name="trigger"
            required
            minLength={3}
            placeholder="application.status_changed"
          />
          <Button type="submit" className="w-full">
            {dictionary.common.create}
          </Button>
        </form>
      </Modal>
    </>
  );
}

export function UniversityAnalytics() {
  const { locale, dictionary } = useI18n();
  const [logs, setLogs] = useState<AIUsageLog[]>([]);
  useEffect(() => {
    apiFetch<AIUsageLog[]>("/ai/usage/logs?limit=100").then(setLogs).catch(() => undefined);
  }, []);
  const total = logs.reduce((sum, item) => sum + item.input_tokens + item.output_tokens, 0);
  const cost = logs.reduce((sum, item) => sum + item.cost_usd, 0);
  return (
    <div className="grid gap-5 xl:grid-cols-[320px_minmax(0,1fr)]">
      <section className="rounded-2xl border bg-white p-5">
        <Robot className="size-6 text-primary" weight="duotone" />
        <p className="mt-5 text-4xl font-semibold tracking-[-0.04em]">
          {total.toLocaleString()}
        </p>
        <p className="mt-2 text-sm text-muted">${cost.toFixed(4)}</p>
      </section>
      <section className="overflow-hidden rounded-2xl border bg-white">
        <div className="border-b p-5">
          <h2 className="font-semibold">{dictionary.sections.analytics}</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px] text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-5 py-3">Feature</th>
                <th className="px-5 py-3">Provider</th>
                <th className="px-5 py-3">Model</th>
                <th className="px-5 py-3">Tokens</th>
                <th className="px-5 py-3">Time</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {logs.map((log) => (
                <tr key={log.id}>
                  <td className="px-5 py-4 font-semibold">{log.feature_name}</td>
                  <td className="px-5 py-4">{log.provider || "deterministic"}</td>
                  <td className="max-w-56 truncate px-5 py-4">{log.model || "—"}</td>
                  <td className="px-5 py-4">
                    {(log.input_tokens + log.output_tokens).toLocaleString()}
                  </td>
                  <td className="px-5 py-4 text-muted">
                    {new Intl.DateTimeFormat(locale, {
                      dateStyle: "short",
                      timeStyle: "short",
                    }).format(new Date(log.created_at))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function graphCount(graph: Record<string, unknown>, key: string): number {
  const value = graph[key];
  return Array.isArray(value) ? value.length : 0;
}
