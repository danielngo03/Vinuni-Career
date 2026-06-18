"use client";

import {
  CalendarDots,
  CheckCircle,
  ClipboardText,
  LockKey,
  VideoCamera,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { apiFetch, apiMessage } from "@/lib/api/client";
import type { Interview, Job, JobApplication, JobPage } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/dashboard/status-badge";

export function ApplicationCenter({ showOnlyInterviews = false }: { showOnlyInterviews?: boolean }) {
  const { dictionary } = useI18n();
  const [applications, setApplications] = useState<JobApplication[]>([]);
  const [interviews, setInterviews] = useState<Interview[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [appData, interviewData, jobData] = await Promise.all([
        apiFetch<JobApplication[]>("/jobs/applications/me"),
        apiFetch<Interview[]>("/interviews"),
        apiFetch<JobPage>("/jobs/page?limit=50&offset=0"),
      ]);
      setApplications(appData);
      setInterviews(interviewData);
      setJobs(jobData.items);
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

  const jobsById = useMemo(
    () => Object.fromEntries(jobs.map((job) => [job.id, job])),
    [jobs],
  );
  const interviewsByApplication = useMemo(
    () =>
      interviews.reduce<Record<string, Interview[]>>((grouped, interview) => {
        (grouped[interview.application_id] ||= []).push(interview);
        return grouped;
      }, {}),
    [interviews],
  );

  async function updateConsent(application: JobApplication) {
    try {
      const updated = await apiFetch<JobApplication>(
        `/jobs/applications/${application.id}/consent`,
        {
          method: "PUT",
          body: JSON.stringify({
            consent_to_unmask: !application.consent_to_unmask,
          }),
        },
      );
      setApplications((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      toast.success(dictionary.common.updated);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    }
  }

  if (showOnlyInterviews) {
    return (
      <section className="rounded-2xl border bg-white p-4 sm:p-5">
        {loading ? <PanelSkeleton /> : null}
        {!loading && !interviews.length ? (
          <EmptyState
            icon={CalendarDots}
            title={dictionary.common.empty}
            description={dictionary.operations.student.applicationsDescription}
          />
        ) : (
          <div className="grid gap-3 lg:grid-cols-2">
            {interviews.map((interview) => (
              <InterviewCard key={interview.id} interview={interview} />
            ))}
          </div>
        )}
      </section>
    );
  }

  return (
    <section className="rounded-2xl border bg-white">
      <div className="border-b p-5">
        <h2 className="font-semibold">{dictionary.sections.applications}</h2>
        <p className="mt-1 text-sm text-muted">
          {dictionary.operations.student.applicationsDescription}
        </p>
      </div>
      <div className="p-4 sm:p-5">
        {loading ? <PanelSkeleton /> : null}
        {!loading && !applications.length ? (
          <EmptyState
            icon={ClipboardText}
            title={dictionary.common.empty}
            description={dictionary.operations.student.applicationsDescription}
          />
        ) : null}
        {!loading && applications.length ? (
          <div className="space-y-4">
            {applications.map((application) => {
              const job = jobsById[application.job_id];
              const relatedInterviews =
                interviewsByApplication[application.id] || [];
              return (
                <article key={application.id} className="rounded-2xl border p-4">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-semibold">
                          {job?.title || application.job_id}
                        </h3>
                        <StatusBadge status={application.status} />
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Badge tone="blue">
                          AI match {Math.round(application.ai_match_score || 0)}%
                        </Badge>
                        <Badge
                          tone={application.consent_to_unmask ? "green" : "gray"}
                        >
                          <LockKey className="mr-1 size-3" />
                          {application.consent_to_unmask
                            ? "PII consent"
                            : "Anonymous"}
                        </Badge>
                      </div>
                      {job?.description ? (
                        <p className="mt-3 line-clamp-2 text-sm leading-6 text-muted">
                          {job.description}
                        </p>
                      ) : null}
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => updateConsent(application)}
                    >
                      {application.consent_to_unmask ? (
                        <LockKey className="size-4" />
                      ) : (
                        <CheckCircle className="size-4" />
                      )}
                      {application.consent_to_unmask
                        ? dictionary.common.cancel
                        : dictionary.common.save}
                    </Button>
                  </div>
                  {relatedInterviews.length ? (
                    <div className="mt-4 grid gap-3 border-t pt-4 lg:grid-cols-2">
                      {relatedInterviews.map((interview) => (
                        <InterviewCard key={interview.id} interview={interview} />
                      ))}
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        ) : null}
      </div>
    </section>
  );
}

function InterviewCard({ interview }: { interview: Interview }) {
  const { locale, dictionary } = useI18n();
  return (
    <article className="rounded-xl bg-slate-50 p-4">
      <div className="flex items-start gap-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-white text-primary shadow-sm">
          <VideoCamera className="size-5" weight="duotone" />
        </div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold">
              {interview.interview_type.replaceAll("_", " ")}
            </p>
            <StatusBadge status={interview.status} />
          </div>
          <p className="mt-1 text-xs leading-5 text-muted">
            {new Intl.DateTimeFormat(locale, {
              dateStyle: "medium",
              timeStyle: "short",
            }).format(new Date(interview.start_time))}
          </p>
          <p className="mt-1 text-xs text-muted">
            {interview.location || interview.meeting_url || dictionary.common.unknown}
          </p>
        </div>
      </div>
    </article>
  );
}
