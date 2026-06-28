"use client";

import {
  CalendarDots,
  ChartBar,
  Check,
  Clock,
  Plus,
  SpinnerGap,
  UsersThree,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { apiFetch, apiMessage } from "@/lib/api/client";
import type { Interview, PartnerDashboard } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { Progress } from "@/components/ui/progress";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/dashboard/status-badge";

const stages = [
  "APPLIED",
  "SHORTLISTED",
  "HR_INTERVIEW",
  "TECH_INTERVIEW",
  "FINAL_INTERVIEW",
  "OFFERED",
];

export function CandidateCenter() {
  const { dictionary } = useI18n();
  const [data, setData] = useState<PartnerDashboard | null>(null);
  const [query, setQuery] = useState("");
  const [workingId, setWorkingId] = useState<string | null>(null);
  const [scheduleId, setScheduleId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await apiFetch<PartnerDashboard>("/dashboard/partner"));
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    }
  }, [dictionary.common.retry]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const candidates = useMemo(
    () =>
      (data?.candidates || []).filter((candidate) =>
        `${candidate.anonymous_label} ${candidate.job_title}`
          .toLowerCase()
          .includes(query.toLowerCase()),
      ),
    [data, query],
  );

  async function move(applicationId: string, currentStatus: string) {
    const currentIndex = stages.indexOf(currentStatus);
    const next = stages[Math.min(stages.length - 1, currentIndex + 1)];
    if (!next || next === currentStatus) return;
    setWorkingId(applicationId);
    try {
      await apiFetch(
        `/jobs/applications/${applicationId}/status?new_status=${next}`,
        { method: "PUT" },
      );
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
    <>
      <section className="rounded-2xl border bg-white">
        <div className="border-b p-5">
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={dictionary.common.search}
            className="max-w-xl rounded-xl bg-slate-50"
          />
        </div>
        <div className="overflow-x-auto p-4 sm:p-5">
          <div className="flex min-w-max gap-3">
            {stages.slice(0, 4).map((stage) => {
              const stageItems = candidates.filter(
                (candidate) =>
                  candidate.status === stage ||
                  (stage === "HR_INTERVIEW" &&
                    ["TECH_INTERVIEW", "FINAL_INTERVIEW"].includes(candidate.status)),
              );
              return (
                <div key={stage} className="w-[280px] rounded-2xl bg-slate-50 p-3">
                  <div className="flex items-center justify-between px-1 py-1">
                    <p className="text-xs font-bold uppercase tracking-wide text-slate-600">
                      {stage.replaceAll("_", " ")}
                    </p>
                    <Badge tone="gray">{stageItems.length}</Badge>
                  </div>
                  <div className="mt-3 space-y-3">
                    {stageItems.map((candidate) => (
                      <article
                        key={candidate.application_id}
                        className="rounded-2xl border bg-white p-4 shadow-[0_10px_24px_-22px_rgba(15,46,96,.8)]"
                      >
                        <div className="flex items-start gap-3">
                          <div className="flex size-9 items-center justify-center rounded-xl bg-blue-50 text-xs font-bold text-primary">
                            {candidate.anonymous_label.slice(-2)}
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="truncate font-semibold">
                              {candidate.anonymous_label}
                            </p>
                            <p className="mt-1 truncate text-xs text-muted">
                              {candidate.job_title}
                            </p>
                          </div>
                        </div>
                        <div className="mt-4">
                          <div className="mb-1 flex justify-between text-xs">
                            <span className="text-muted">AI match</span>
                            <span className="font-semibold text-success">
                              {Math.round(candidate.ai_match_score || 0)}%
                            </span>
                          </div>
                          <Progress
                            value={candidate.ai_match_score || 0}
                            indicatorClassName="bg-success"
                          />
                        </div>
                        <div className="mt-4 flex items-center gap-2">
                          <Badge
                            tone={candidate.consent_to_unmask ? "green" : "gray"}
                          >
                            {candidate.consent_to_unmask ? (
                              <Check className="mr-1 size-3" />
                            ) : null}
                            {candidate.consent_to_unmask ? "PII consent" : "Anonymous"}
                          </Badge>
                          {stage === "HR_INTERVIEW" ? (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="ml-auto"
                              onClick={() => setScheduleId(candidate.application_id)}
                            >
                              <CalendarDots className="size-4" />
                            </Button>
                          ) : (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="ml-auto"
                              onClick={() =>
                                move(candidate.application_id, candidate.status)
                              }
                              disabled={workingId === candidate.application_id}
                            >
                              {workingId === candidate.application_id ? (
                                <SpinnerGap className="size-4 animate-spin" />
                              ) : (
                                dictionary.common.open
                              )}
                            </Button>
                          )}
                        </div>
                      </article>
                    ))}
                    {!stageItems.length ? (
                      <div className="rounded-xl border border-dashed bg-white/70 p-6 text-center text-xs text-muted">
                        {dictionary.common.empty}
                      </div>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>
      <InterviewModal
        applicationId={scheduleId}
        onOpenChange={(open) => !open && setScheduleId(null)}
      />
    </>
  );
}

export function PartnerInterviewCenter() {
  const { locale, dictionary } = useI18n();
  const [items, setItems] = useState<Interview[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch<Interview[]>("/interviews")
      .then(setItems)
      .catch((error) => toast.error(apiMessage(error, dictionary.common.retry)))
      .finally(() => setLoading(false));
  }, [dictionary.common.retry]);

  return (
    <section className="rounded-2xl border bg-white p-4 sm:p-5">
      {loading ? <PanelSkeleton /> : null}
      {!loading && !items.length ? (
        <EmptyState
          icon={CalendarDots}
          title={dictionary.common.empty}
          description={dictionary.operations.partner.interviewsDescription}
        />
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {items.map((interview) => (
            <article key={interview.id} className="rounded-2xl border p-4">
              <div className="flex items-start gap-3">
                <div className="flex size-10 items-center justify-center rounded-xl bg-blue-50 text-primary">
                  <Clock className="size-5" weight="duotone" />
                </div>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-semibold">
                      {interview.interview_type.replaceAll("_", " ")}
                    </p>
                    <StatusBadge status={interview.status} />
                  </div>
                  <p className="mt-2 text-sm text-muted">
                    {new Intl.DateTimeFormat(locale, {
                      dateStyle: "medium",
                      timeStyle: "short",
                    }).format(new Date(interview.start_time))}
                  </p>
                  <p className="mt-1 text-xs text-muted">
                    {interview.location || interview.meeting_url}
                  </p>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

export function PartnerAnalytics() {
  const { dictionary } = useI18n();
  const [data, setData] = useState<PartnerDashboard | null>(null);
  useEffect(() => {
    apiFetch<PartnerDashboard>("/dashboard/partner").then(setData).catch(() => undefined);
  }, []);
  if (!data) return <PanelSkeleton />;
  const total = Math.max(
    1,
    (data.application_distribution || []).reduce((sum, item) => sum + item.value, 0),
  );
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <section className="rounded-2xl border bg-white p-5">
        <div className="flex items-center gap-2">
          <UsersThree className="size-5 text-primary" weight="duotone" />
          <h2 className="font-semibold">{dictionary.sections.candidates}</h2>
        </div>
        <div className="mt-5 space-y-4">
          {(data.application_distribution || []).map((point) => (
            <div key={point.label}>
              <div className="mb-1.5 flex justify-between text-sm">
                <span>{point.label.replaceAll("_", " ")}</span>
                <span className="font-semibold">{point.value}</span>
              </div>
              <Progress value={(point.value / total) * 100} />
            </div>
          ))}
        </div>
      </section>
      <section className="rounded-2xl border bg-white p-5">
        <div className="flex items-center gap-2">
          <ChartBar className="size-5 text-primary" weight="duotone" />
          <h2 className="font-semibold">{dictionary.sections.analytics}</h2>
        </div>
        <p className="mt-6 text-4xl font-semibold tracking-[-0.04em]">
          {Number(data.ai_usage.total_tokens || 0).toLocaleString()}
        </p>
        <p className="mt-2 text-sm text-muted">
          ${(data.ai_usage.estimated_cost_usd || 0).toFixed(4)}
        </p>
      </section>
    </div>
  );
}

function InterviewModal({
  applicationId,
  onOpenChange,
}: {
  applicationId: string | null;
  onOpenChange: (open: boolean) => void;
}) {
  const { dictionary } = useI18n();
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!applicationId) return;
    const form = new FormData(event.currentTarget);
    const start = new Date(String(form.get("start")));
    const end = new Date(start.getTime() + 60 * 60 * 1000);
    try {
      await apiFetch("/interviews", {
        method: "POST",
        body: JSON.stringify({
          application_id: applicationId,
          interview_type: "HR_ROUND",
          start_time: start.toISOString(),
          end_time: end.toISOString(),
          meeting_url: form.get("meeting_url"),
          notes: form.get("notes"),
        }),
      });
      onOpenChange(false);
      toast.success(dictionary.common.updated);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    }
  }
  return (
    <Modal
      open={Boolean(applicationId)}
      onOpenChange={onOpenChange}
      title={dictionary.sections.interviews}
      description={dictionary.operations.partner.interviewsDescription}
    >
      <form onSubmit={submit} className="space-y-4">
        <Input name="start" type="datetime-local" required />
        <Input name="meeting_url" type="url" placeholder="https://meet..." />
        <textarea
          name="notes"
          className="focus-ring min-h-24 w-full rounded-xl border p-3 text-sm"
          placeholder={dictionary.forms.notes}
        />
        <Button className="w-full" type="submit">
          <Plus className="size-4" />
          {dictionary.common.create}
        </Button>
      </form>
    </Modal>
  );
}
