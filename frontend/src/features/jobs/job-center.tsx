"use client";

import {
  BookmarkSimple,
  Briefcase,
  CheckCircle,
  Funnel,
  ChatCircleText,
  MagnifyingGlass,
  Plus,
  SpinnerGap,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { apiFetch, apiMessage } from "@/lib/api/client";
import type { CV, Job, JobPage, Portal } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/dashboard/status-badge";
import { InterviewSimulatorModal } from "@/features/jobs/interview-simulator-modal";

export function JobCenter({
  portal,
  orgId,
}: {
  portal: Portal;
  orgId?: string | null;
}) {
  const { dictionary } = useI18n();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [cvs, setCvs] = useState<CV[]>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [workingId, setWorkingId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [interviewJob, setInterviewJob] = useState<Job | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "50", offset: "0" });
      if (portal === "partner" && orgId) params.set("org_id", orgId);
      if (status) params.set("status", status);
      const requests: [Promise<JobPage>, Promise<CV[]> | null] = [
        apiFetch<JobPage>(`/jobs/page?${params}`),
        portal === "student" ? apiFetch<CV[]>("/cvs/me") : null,
      ];
      const [jobPage, cvData] = await Promise.all([
        requests[0],
        requests[1] || Promise.resolve([]),
      ]);
      setJobs(jobPage.items);
      setCvs(cvData);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setLoading(false);
    }
  }, [dictionary.common.retry, orgId, portal, status]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return jobs;
    return jobs.filter((job) =>
      [job.title, job.description, ...(job.skills || [])]
        .join(" ")
        .toLowerCase()
        .includes(normalized),
    );
  }, [jobs, query]);

  async function apply(jobId: string) {
    const cv = cvs.find((item) => item.is_primary) || cvs[0];
    if (!cv) {
      toast.error(dictionary.operations.student.cvDescription);
      return;
    }
    setWorkingId(jobId);
    try {
      await apiFetch(`/jobs/${jobId}/applications`, {
        method: "POST",
        body: JSON.stringify({ cv_id: cv.id, consent_to_unmask: false }),
      });
      toast.success(dictionary.common.updated);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setWorkingId(null);
    }
  }

  async function bookmark(jobId: string) {
    setWorkingId(jobId);
    try {
      await apiFetch(`/jobs/${jobId}/bookmarks`, { method: "POST" });
      toast.success(dictionary.jobs.saved);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setWorkingId(null);
    }
  }

  async function moderate(jobId: string, approve: boolean) {
    setWorkingId(jobId);
    try {
      await apiFetch(`/jobs/${jobId}/moderate`, {
        method: "POST",
        body: JSON.stringify({
          approve,
          reason: approve
            ? "Approved after university review."
            : "Requires clarification before publication.",
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

  return (
    <>
      <section className="rounded-2xl border bg-white">
        <div className="flex flex-col gap-3 border-b p-5 lg:flex-row lg:items-center">
          <div className="relative min-w-0 flex-1 lg:max-w-xl">
            <MagnifyingGlass className="absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={dictionary.jobs.searchPlaceholder}
              className="h-11 rounded-xl bg-slate-50 pl-10"
            />
          </div>
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            className="focus-ring h-11 rounded-xl border bg-white px-3 text-sm"
            aria-label={dictionary.common.status}
          >
            <option value="">{dictionary.common.all}</option>
            <option value="APPROVED">APPROVED</option>
            <option value="PENDING_APPROVAL">PENDING APPROVAL</option>
            <option value="REJECTED">REJECTED</option>
          </select>
          {portal === "partner" ? (
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="size-4" />
              {dictionary.jobs.create}
            </Button>
          ) : (
            <Button variant="outline">
              <Funnel className="size-4" />
              {dictionary.common.status}
            </Button>
          )}
        </div>
        <div className="p-4 sm:p-5">
          {loading ? <PanelSkeleton /> : null}
          {!loading && !filtered.length ? (
            <EmptyState
              icon={Briefcase}
              title={dictionary.jobs.noJobs}
              description={dictionary.jobs.noJobsDescription}
            />
          ) : null}
          {!loading && filtered.length ? (
            <div className="grid gap-3">
              {filtered.map((job) => (
                <article
                  key={job.id}
                  className="group grid gap-4 rounded-2xl border p-4 transition-all hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-[0_14px_30px_-26px_rgba(15,92,229,.8)] md:grid-cols-[minmax(0,1fr)_auto] md:items-center"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold">{job.title}</h3>
                      <StatusBadge status={job.status} />
                      {job.job_type ? <Badge tone="blue">{job.job_type}</Badge> : null}
                    </div>
                    <p className="mt-2 line-clamp-2 text-sm leading-6 text-muted">
                      {job.description}
                    </p>
                    <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted">
                      <span>{job.location_address || dictionary.common.unknown}</span>
                      <span>•</span>
                      <span>{job.location_type || dictionary.common.unknown}</span>
                      {job.application_deadline ? (
                        <>
                          <span>•</span>
                          <span>
                            {dictionary.jobs.deadline}:{" "}
                            {new Date(job.application_deadline).toLocaleDateString()}
                          </span>
                        </>
                      ) : null}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {(job.skills || []).slice(0, 6).map((skill) => (
                        <Badge key={skill} tone="gray">
                          {skill}
                        </Badge>
                      ))}
                    </div>
                  </div>
                  <div className="flex flex-wrap justify-end gap-2">
                    {portal === "student" ? (
                      <>
                        <Button
                          variant="outline"
                          size="icon"
                          onClick={() => bookmark(job.id)}
                          aria-label={dictionary.jobs.save}
                          disabled={workingId === job.id}
                        >
                          <BookmarkSimple className="size-4" />
                        </Button>
                        <Button
                          variant="outline"
                          onClick={() => setInterviewJob(job)}
                          disabled={workingId === job.id}
                        >
                          <ChatCircleText className="size-4" />
                          Phỏng vấn thử
                        </Button>
                        <Button
                          onClick={() => apply(job.id)}
                          disabled={workingId === job.id}
                        >
                          {workingId === job.id ? (
                            <SpinnerGap className="size-4 animate-spin" />
                          ) : (
                            <CheckCircle className="size-4" />
                          )}
                          {dictionary.jobs.apply}
                        </Button>
                      </>
                    ) : null}
                    {portal === "university" && job.status === "PENDING_APPROVAL" ? (
                      <>
                        <Button
                          variant="danger"
                          size="sm"
                          onClick={() => moderate(job.id, false)}
                          disabled={workingId === job.id}
                        >
                          {dictionary.common.cancel}
                        </Button>
                        <Button
                          size="sm"
                          onClick={() => moderate(job.id, true)}
                          disabled={workingId === job.id}
                        >
                          {dictionary.common.save}
                        </Button>
                      </>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
          ) : null}
        </div>
      </section>
      <CreateJobModal
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={load}
      />
      <InterviewSimulatorModal
        open={Boolean(interviewJob)}
        onOpenChange={(open) => {
          if (!open) setInterviewJob(null);
        }}
        job={interviewJob}
        cv={cvs.find((item) => item.is_primary) || cvs[0] || null}
      />
    </>
  );
}

function CreateJobModal({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => Promise<void>;
}) {
  const { dictionary } = useI18n();
  const [pending, setPending] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setPending(true);
    try {
      await apiFetch("/jobs", {
        method: "POST",
        body: JSON.stringify({
          title: form.get("title"),
          description: form.get("description"),
          requirements: form.get("requirements"),
          location_address: form.get("location"),
          job_type: "INTERNSHIP",
          location_type: "HYBRID",
          skills: String(form.get("skills") || "")
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean),
        }),
      });
      await onCreated();
      onOpenChange(false);
      toast.success(dictionary.common.updated);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setPending(false);
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={dictionary.jobs.create}
      description={dictionary.operations.partner.jobsDescription}
    >
      <form onSubmit={submit} className="space-y-4">
        <Field label={dictionary.forms.title}>
          <Input name="title" required minLength={3} />
        </Field>
        <Field label={dictionary.forms.location}>
          <Input name="location" />
        </Field>
        <Field label={dictionary.forms.skills}>
          <Input name="skills" placeholder="Python, SQL, FastAPI" />
        </Field>
        <Field label={dictionary.forms.description}>
          <textarea
            name="description"
            required
            minLength={80}
            className="focus-ring min-h-32 w-full rounded-xl border p-3 text-sm"
          />
        </Field>
        <Field label={dictionary.ai.jdAnalysis}>
          <textarea
            name="requirements"
            className="focus-ring min-h-24 w-full rounded-xl border p-3 text-sm"
          />
        </Field>
        <Button type="submit" className="w-full" disabled={pending}>
          {pending ? <SpinnerGap className="size-4 animate-spin" /> : <Plus className="size-4" />}
          {pending ? dictionary.forms.submitting : dictionary.jobs.create}
        </Button>
      </form>
    </Modal>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-sm font-semibold">{label}</span>
      {children}
    </label>
  );
}
