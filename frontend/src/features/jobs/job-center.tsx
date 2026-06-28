"use client";

import {
  BookmarkSimple,
  Briefcase,
  CheckCircle,
  FileText,
  Funnel,
  ChatCircleText,
  MagnifyingGlass,
  PencilSimple,
  Plus,
  Robot,
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
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [rawDraft, setRawDraft] = useState("");
  const [rawEditing, setRawEditing] = useState(false);
  const [analyzingId, setAnalyzingId] = useState<string | null>(null);
  const [creatingBlank, setCreatingBlank] = useState(false);

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

  const selectedJob = useMemo(
    () => jobs.find((job) => job.id === selectedJobId) || jobs[0] || null,
    [jobs, selectedJobId],
  );

  useEffect(() => {
    if (portal !== "partner") return;
    if (!jobs.length) {
      setSelectedJobId(null);
      setRawDraft("");
      return;
    }
    if (!selectedJobId || !jobs.some((job) => job.id === selectedJobId)) {
      setSelectedJobId(jobs[0].id);
    }
  }, [jobs, portal, selectedJobId]);

  useEffect(() => {
    if (portal !== "partner" || !selectedJob || rawEditing) return;
    setRawDraft(rawTextForJob(selectedJob));
  }, [portal, rawEditing, selectedJob]);

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

  function selectJob(job: Job) {
    setSelectedJobId(job.id);
    setRawDraft(rawTextForJob(job));
    setRawEditing(false);
  }

  async function createBlankJob() {
    setCreatingBlank(true);
    try {
      const job = await apiFetch<Job>("/jobs/blank", { method: "POST" });
      setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)]);
      setSelectedJobId(job.id);
      setRawDraft(rawTextForJob(job));
      setRawEditing(true);
      toast.success(dictionary.common.updated);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setCreatingBlank(false);
    }
  }

  async function saveSelectedJob(job: Job, analyzeAfterSave = false) {
    if (!rawDraft.trim()) {
      toast.error(dictionary.forms.required);
      return;
    }
    setWorkingId(job.id);
    try {
      const updated = await apiFetch<Job>(`/jobs/${job.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          title: firstHeading(rawDraft) || job.title,
          description: rawDraft.trim(),
        }),
      });
      setJobs((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      toast.success(dictionary.common.updated);
      if (analyzeAfterSave) await analyzeJob(updated);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setWorkingId(null);
    }
  }

  async function analyzeJob(job: Job) {
    setAnalyzingId(job.id);
    try {
      const updated = await apiFetch<Job>(`/jobs/${job.id}/reanalyze`, {
        method: "POST",
      });
      setJobs((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setSelectedJobId(updated.id);
      setRawDraft(rawTextForJob(updated));
      setRawEditing(false);
      toast.success(dictionary.ai.completed);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.ai.failed));
    } finally {
      setAnalyzingId(null);
    }
  }

  if (portal === "partner") {
    return (
      <>
        <PartnerJobWorkspace
          jobs={filtered}
          selectedJob={selectedJob}
          rawDraft={rawDraft}
          rawEditing={rawEditing}
          loading={loading}
          creatingBlank={creatingBlank}
          workingId={workingId}
          analyzingId={analyzingId}
          query={query}
          status={status}
          onQueryChange={setQuery}
          onStatusChange={setStatus}
          onCreate={() => setCreateOpen(true)}
          onCreateBlank={createBlankJob}
          onSelect={selectJob}
          onRawDraftChange={setRawDraft}
          onRawEditingChange={setRawEditing}
          onSave={(job) => saveSelectedJob(job)}
          onAnalyze={(job) => saveSelectedJob(job, true)}
        />
        <CreateJobModal
          open={createOpen}
          onOpenChange={setCreateOpen}
          onCreated={load}
        />
      </>
    );
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
          <Button variant="outline">
            <Funnel className="size-4" />
            {dictionary.common.status}
          </Button>
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

function PartnerJobWorkspace({
  jobs,
  selectedJob,
  rawDraft,
  rawEditing,
  loading,
  creatingBlank,
  workingId,
  analyzingId,
  query,
  status,
  onQueryChange,
  onStatusChange,
  onCreate,
  onCreateBlank,
  onSelect,
  onRawDraftChange,
  onRawEditingChange,
  onSave,
  onAnalyze,
}: {
  jobs: Job[];
  selectedJob: Job | null;
  rawDraft: string;
  rawEditing: boolean;
  loading: boolean;
  creatingBlank: boolean;
  workingId: string | null;
  analyzingId: string | null;
  query: string;
  status: string;
  onQueryChange: (value: string) => void;
  onStatusChange: (value: string) => void;
  onCreate: () => void;
  onCreateBlank: () => void;
  onSelect: (job: Job) => void;
  onRawDraftChange: (value: string) => void;
  onRawEditingChange: (value: boolean) => void;
  onSave: (job: Job) => void;
  onAnalyze: (job: Job) => void;
}) {
  const { dictionary } = useI18n();
  const selectedAnalyzing = selectedJob ? analyzingId === selectedJob.id : false;

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
      <section className="rounded-2xl border bg-white">
        <div className="flex flex-col gap-3 border-b p-5 lg:flex-row lg:items-center">
          <div className="min-w-0 flex-1">
            <h2 className="font-semibold">{dictionary.operations.partner.jobsTitle}</h2>
            <p className="mt-1 text-sm text-muted">
              {dictionary.operations.partner.jobsDescription}
            </p>
          </div>
          <Button onClick={onCreateBlank} variant="outline" disabled={creatingBlank}>
            {creatingBlank ? (
              <SpinnerGap className="size-4 animate-spin" />
            ) : (
              <FileText className="size-4" />
            )}
            Tạo JD rỗng
          </Button>
          <Button onClick={onCreate}>
            <Plus className="size-4" />
            {dictionary.jobs.create}
          </Button>
        </div>
        <div className="p-4 sm:p-5">
          {loading ? <PanelSkeleton /> : null}
          {!loading && !selectedJob ? (
            <EmptyState
              icon={Briefcase}
              title={dictionary.jobs.noJobs}
              description={dictionary.jobs.noJobsDescription}
            />
          ) : null}
          {!loading && selectedJob ? (
            <div>
              <div className="flex flex-col gap-3 border-b pb-4 sm:flex-row sm:items-start">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-semibold">{selectedJob.title}</h3>
                    <StatusBadge status={selectedJob.status} />
                    {selectedJob.job_type ? <Badge tone="blue">{selectedJob.job_type}</Badge> : null}
                    {selectedAnalyzing ? (
                      <Badge tone="amber">
                        <SpinnerGap className="mr-1 size-3 animate-spin" />
                        Đang phân tích
                      </Badge>
                    ) : null}
                  </div>
                  <p className="mt-2 text-xs text-muted">
                    {selectedJob.location_address || dictionary.common.unknown}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant={rawEditing ? "outline" : "ghost"}
                    size="sm"
                    onClick={() => onRawEditingChange(!rawEditing)}
                  >
                    <PencilSimple className="size-4" />
                    {rawEditing ? "Xem Markdown" : "Edit"}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onSave(selectedJob)}
                    disabled={workingId === selectedJob.id || selectedAnalyzing}
                  >
                    {workingId === selectedJob.id ? (
                      <SpinnerGap className="size-4 animate-spin" />
                    ) : (
                      <CheckCircle className="size-4" />
                    )}
                    {dictionary.common.save}
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => onAnalyze(selectedJob)}
                    disabled={workingId === selectedJob.id || selectedAnalyzing}
                  >
                    {selectedAnalyzing ? (
                      <SpinnerGap className="size-4 animate-spin" />
                    ) : (
                      <Robot className="size-4" weight="duotone" />
                    )}
                    {selectedAnalyzing ? "Đang phân tích" : "Phân tích lại"}
                  </Button>
                </div>
              </div>

              <div className="relative">
                {selectedAnalyzing ? (
                  <div className="pointer-events-none absolute right-4 top-8 z-10 inline-flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800 shadow-sm">
                    <SpinnerGap className="size-4 animate-spin" />
                    AI đang phân tích JD này
                  </div>
                ) : null}
                {rawEditing ? (
                  <textarea
                    value={rawDraft}
                    onChange={(event) => onRawDraftChange(event.target.value)}
                    className="focus-ring mt-4 min-h-[520px] w-full resize-y rounded-xl border bg-slate-50 p-4 font-mono text-sm leading-6"
                    spellCheck={false}
                  />
                ) : (
                  <MarkdownPreview content={rawDraft} busy={selectedAnalyzing} />
                )}
              </div>
            </div>
          ) : null}
        </div>
      </section>

      <section className="rounded-2xl border bg-white p-5">
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-semibold">Chọn JD</h2>
          <Badge tone="blue">{jobs.length}</Badge>
        </div>
        <div className="relative mt-4">
          <MagnifyingGlass className="absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted" />
          <Input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder={dictionary.jobs.searchPlaceholder}
            className="h-10 rounded-xl bg-slate-50 pl-10"
          />
        </div>
        <select
          value={status}
          onChange={(event) => onStatusChange(event.target.value)}
          className="focus-ring mt-3 h-10 w-full rounded-xl border bg-white px-3 text-sm"
          aria-label={dictionary.common.status}
        >
          <option value="">{dictionary.common.all}</option>
          <option value="DRAFT">DRAFT</option>
          <option value="APPROVED">APPROVED</option>
          <option value="PENDING_APPROVAL">PENDING APPROVAL</option>
          <option value="REJECTED">REJECTED</option>
        </select>
        <div className="mt-5 space-y-3">
          {loading ? <PanelSkeleton /> : null}
          {jobs.map((job) => (
            <button
              key={job.id}
              type="button"
              className={`w-full rounded-xl border p-3 text-left transition-colors ${
                selectedJob?.id === job.id ? "border-blue-300 bg-blue-50/50" : "bg-white"
              }`}
              onClick={() => onSelect(job)}
            >
              <div className="flex items-start gap-3">
                <FileText className="mt-0.5 size-5 shrink-0 text-primary" weight="duotone" />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <p className="truncate text-sm font-semibold">{job.title}</p>
                    <StatusBadge status={job.status} />
                    {analyzingId === job.id ? (
                      <Badge tone="amber" className="px-1.5 py-0.5">
                        <SpinnerGap className="mr-1 size-3 animate-spin" />
                        Đang chạy
                      </Badge>
                    ) : null}
                  </div>
                  <p className="mt-1 text-xs text-muted">
                    {job.location_address || dictionary.common.unknown}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {(job.skills || []).length ? (
                      (job.skills || []).slice(0, 8).map((skill) => (
                        <Badge key={skill} tone="blue" className="px-1.5 py-0.5">
                          {skill}
                        </Badge>
                      ))
                    ) : (
                      <span className="text-xs text-muted">{dictionary.common.empty}</span>
                    )}
                  </div>
                </div>
              </div>
            </button>
          ))}
          {!jobs.length && !loading ? (
            <p className="rounded-xl bg-slate-50 p-4 text-sm text-muted">
              {dictionary.jobs.noJobsDescription}
            </p>
          ) : null}
        </div>
      </section>
    </div>
  );
}

function rawTextForJob(job: Job) {
  return [
    job.description || `# ${job.title}`,
    job.requirements ? `## Requirements\n${job.requirements}` : "",
    job.responsibilities ? `## Responsibilities\n${job.responsibilities}` : "",
    job.benefits_text ? `## Benefits\n${job.benefits_text}` : "",
  ]
    .filter(Boolean)
    .join("\n\n");
}

function firstHeading(markdown: string) {
  const heading = markdown
    .split(/\r?\n/)
    .find((line) => line.startsWith("# ") && line.slice(2).trim());
  return heading?.slice(2).trim();
}

function MarkdownPreview({ content, busy = false }: { content: string; busy?: boolean }) {
  const lines = content.split(/\r?\n/);
  return (
    <div
      className={`mt-4 min-h-[520px] rounded-xl border bg-slate-50 p-5 transition-opacity ${
        busy ? "opacity-70" : "opacity-100"
      }`}
    >
      <div className="space-y-2 text-sm leading-7 text-slate-700">
        {lines.map((line, index) => {
          const key = `${index}-${line}`;
          if (!line.trim()) return <div key={key} className="h-2" />;
          if (line.startsWith("# ")) {
            return (
              <h1 key={key} className="text-2xl font-semibold leading-tight text-slate-950">
                {line.slice(2)}
              </h1>
            );
          }
          if (line.startsWith("## ")) {
            return (
              <h2 key={key} className="pt-3 text-lg font-semibold leading-tight text-slate-950">
                {line.slice(3)}
              </h2>
            );
          }
          if (line.startsWith("### ")) {
            return (
              <h3 key={key} className="pt-2 font-semibold leading-tight text-slate-900">
                {line.slice(4)}
              </h3>
            );
          }
          if (line.startsWith("- ")) {
            return (
              <p key={key} className="pl-4">
                <span className="mr-2 text-primary">•</span>
                {line.slice(2)}
              </p>
            );
          }
          return <p key={key}>{line}</p>;
        })}
      </div>
    </div>
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
