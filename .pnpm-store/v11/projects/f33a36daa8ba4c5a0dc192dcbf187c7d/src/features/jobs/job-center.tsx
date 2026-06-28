"use client";

import {
  BookmarkSimple,
  Briefcase,
  CalendarBlank,
  CheckCircle,
  FloppyDisk,
  FileText,
  Funnel,
  ChatCircleText,
  MagnifyingGlass,
  Plus,
  SpinnerGap,
  UploadSimple,
  XCircle,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { apiFetch, apiMessage } from "@/lib/api/client";
import type { CV, Job, JobApplication, JobPage, Portal } from "@/lib/api/types";
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
  const [detailJob, setDetailJob] = useState<Job | null>(null);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [partnerDetailTab, setPartnerDetailTab] = useState<PartnerJobTab>("content");
  const [analysisDraft, setAnalysisDraft] = useState<JobAnalysisDraft>(() =>
    emptyJobAnalysisDraft(),
  );
  const [schedules, setSchedules] = useState<JobSchedule[]>([]);
  const [scheduleClock, setScheduleClock] = useState<JobScheduleClock | null>(null);
  const [scheduleLoading, setScheduleLoading] = useState(false);
  const [applications, setApplications] = useState<JobApplication[]>([]);
  const [applicationsLoading, setApplicationsLoading] = useState(false);

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
    const results = normalized
      ? jobs.filter((job) =>
          [job.title, job.description, ...(job.skills || [])]
            .join(" ")
            .toLowerCase()
            .includes(normalized),
        )
      : jobs;
    return portal === "student"
      ? [...results].sort((a, b) => (b.match_score ?? -1) - (a.match_score ?? -1))
      : results;
  }, [jobs, portal, query]);

  const selectedJob = useMemo(
    () => jobs.find((job) => job.id === selectedJobId) || jobs[0] || null,
    [jobs, selectedJobId],
  );
  const selectedSavedAnalysis = selectedJob
    ? analysisDraftFromJob(selectedJob)
    : emptyJobAnalysisDraft();
  const selectedHasUnsavedChanges = selectedJob
    ? serializeAnalysisDraft(analysisDraft) !== serializeAnalysisDraft(selectedSavedAnalysis)
    : false;
  useEffect(() => {
    if (portal !== "partner") return;
    if (!jobs.length) {
      setSelectedJobId(null);
      setAnalysisDraft(emptyJobAnalysisDraft());
      return;
    }
    if (!selectedJobId || !jobs.some((job) => job.id === selectedJobId)) {
      setSelectedJobId(jobs[0].id);
    }
  }, [jobs, portal, selectedJobId]);

  useEffect(() => {
    if (portal !== "partner" || !selectedJob) return;
    setAnalysisDraft(analysisDraftFromJob(selectedJob));
  }, [portal, selectedJob]);

  useEffect(() => {
    if (portal !== "partner" || !selectedJob) {
      setSchedules([]);
      setApplications([]);
      return;
    }
    void loadScheduleClock();
    void loadSchedules(selectedJob.id);
    void loadApplications(selectedJob.id);
  }, [portal, selectedJob?.id]);

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
    setAnalysisDraft(analysisDraftFromJob(job));
    setPartnerDetailTab("content");
  }

  async function saveSelectedJob(job: Job) {
    setWorkingId(job.id);
    try {
      const updated = await apiFetch<Job>(`/jobs/${job.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          title: analysisDraft.title.trim() || job.title,
          description: analysisDraft.description.trim() || job.description,
          requirements: requirementsTextFromDraft(analysisDraft),
          responsibilities: linesToText(analysisDraft.responsibilities),
          location_address: analysisDraft.location.trim() || job.location_address,
          skills: skillsFromDraft(analysisDraft),
          parsed_requirements: parsedRequirementsFromDraft(analysisDraft),
        }),
      });
      setJobs((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      setAnalysisDraft(analysisDraftFromJob(updated));
      toast.success(dictionary.common.updated);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setWorkingId(null);
    }
  }

  async function runManualJobAction(job: Job, action: JobScheduleAction) {
    setWorkingId(job.id);
    try {
      const updated = await apiFetch<Job>(`/jobs/${job.id}/actions`, {
        method: "POST",
        body: JSON.stringify({ action }),
      });
      setJobs((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setSelectedJobId(updated.id);
      toast.success(dictionary.common.updated);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setWorkingId(null);
    }
  }

  async function loadSchedules(jobId: string) {
    setScheduleLoading(true);
    try {
      setSchedules(await apiFetch<JobSchedule[]>(`/jobs/${jobId}/schedules`));
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setScheduleLoading(false);
    }
  }

  async function loadScheduleClock() {
    try {
      setScheduleClock(await apiFetch<JobScheduleClock>("/jobs/schedules/clock"));
    } catch {
      setScheduleClock(null);
    }
  }

  async function createSchedule(job: Job, action: JobScheduleAction, localDateTime: string) {
    if (!localDateTime) {
      toast.error(dictionary.forms.required);
      return;
    }
    setWorkingId(job.id);
    try {
      await apiFetch<JobSchedule>(`/jobs/${job.id}/schedules`, {
        method: "POST",
        body: JSON.stringify({
          action,
          run_at: backendLocalDateTime(localDateTime),
        }),
      });
      await loadSchedules(job.id);
      toast.success(dictionary.common.updated);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setWorkingId(null);
    }
  }

  async function cancelSchedule(job: Job, scheduleId: string) {
    setWorkingId(job.id);
    try {
      await apiFetch<JobSchedule>(`/jobs/${job.id}/schedules/${scheduleId}`, {
        method: "DELETE",
      });
      await loadSchedules(job.id);
      toast.success(dictionary.common.updated);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setWorkingId(null);
    }
  }

  async function loadApplications(jobId: string) {
    setApplicationsLoading(true);
    try {
      setApplications(await apiFetch<JobApplication[]>(`/jobs/${jobId}/applications`));
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setApplicationsLoading(false);
    }
  }

  async function updateApplicationStatus(
    job: Job,
    applicationId: string,
    newStatus: string,
  ) {
    setWorkingId(job.id);
    try {
      await apiFetch<JobApplication>(
        `/jobs/applications/${applicationId}/status?new_status=${encodeURIComponent(newStatus)}`,
        { method: "PUT" },
      );
      await loadApplications(job.id);
      await load();
      toast.success(dictionary.common.updated);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setWorkingId(null);
    }
  }

  if (portal === "partner") {
    return (
      <>
        <PartnerJobWorkspace
          jobs={filtered}
          selectedJob={selectedJob}
          analysisDraft={analysisDraft}
          loading={loading}
          workingId={workingId}
          schedules={schedules}
          scheduleClock={scheduleClock}
          scheduleLoading={scheduleLoading}
          applications={applications}
          applicationsLoading={applicationsLoading}
          detailTab={partnerDetailTab}
          hasUnsavedChanges={selectedHasUnsavedChanges}
          query={query}
          status={status}
          onQueryChange={setQuery}
          onStatusChange={setStatus}
          onCreate={() => setCreateOpen(true)}
          onSelect={selectJob}
          onAnalysisDraftChange={setAnalysisDraft}
          onDetailTabChange={setPartnerDetailTab}
          onSave={saveSelectedJob}
          onManualAction={runManualJobAction}
          onCreateSchedule={createSchedule}
          onCancelSchedule={cancelSchedule}
          onUpdateApplicationStatus={updateApplicationStatus}
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
                  role={portal === "student" ? "button" : undefined}
                  tabIndex={portal === "student" ? 0 : undefined}
                  onClick={portal === "student" ? () => setDetailJob(job) : undefined}
                  onKeyDown={portal === "student" ? (event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setDetailJob(job);
                    }
                  } : undefined}
                  className={`group grid gap-4 rounded-2xl border p-4 transition-all hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-[0_14px_30px_-26px_rgba(15,92,229,.8)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 md:items-center ${
                    portal === "student"
                      ? "md:grid-cols-[minmax(0,1fr)_9rem_auto]"
                      : "md:grid-cols-[minmax(0,1fr)_auto]"
                  }`}
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
                  {portal === "student" ? (
                    <div className="flex md:justify-center">
                      {typeof job.match_score === "number" ? (
                        <div className="min-w-28 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-2 text-center text-white shadow-sm">
                          <div className="text-xl font-bold leading-none">{Math.round(job.match_score)}%</div>
                          <div className="mt-1 text-xs font-medium text-blue-50">phù hợp</div>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  <div className="flex flex-wrap justify-end gap-2">
                    {portal === "student" ? (
                      <>
                        <Button
                          variant="outline"
                          size="icon"
                          onClick={(event) => {
                            event.stopPropagation();
                            void bookmark(job.id);
                          }}
                          aria-label={dictionary.jobs.save}
                          disabled={workingId === job.id}
                        >
                          <BookmarkSimple className="size-4" />
                        </Button>
                        <Button
                          variant="outline"
                          onClick={(event) => {
                            event.stopPropagation();
                            setInterviewJob(job);
                          }}
                          disabled={workingId === job.id}
                        >
                          <ChatCircleText className="size-4" />
                          Phỏng vấn thử
                        </Button>
                        <Button
                          onClick={(event) => {
                            event.stopPropagation();
                            void apply(job.id);
                          }}
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
      <StudentJobDetailModal
        job={detailJob}
        open={Boolean(detailJob)}
        working={detailJob ? workingId === detailJob.id : false}
        onOpenChange={(open) => {
          if (!open) setDetailJob(null);
        }}
        onBookmark={(job) => void bookmark(job.id)}
        onInterview={setInterviewJob}
        onApply={(job) => void apply(job.id)}
      />
    </>
  );
}

function StudentJobDetailModal({
  job, open, working, onOpenChange, onBookmark, onInterview, onApply,
}: {
  job: Job | null;
  open: boolean;
  working: boolean;
  onOpenChange: (open: boolean) => void;
  onBookmark: (job: Job) => void;
  onInterview: (job: Job) => void;
  onApply: (job: Job) => void;
}) {
  if (!job) return null;
  const salary = job.salary_min || job.salary_max
    ? `${job.salary_min?.toLocaleString() || "0"} – ${job.salary_max?.toLocaleString() || "∞"} ${job.currency}`
    : "Thỏa thuận";

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={job.title}
      description={`${job.location_address || "Chưa cập nhật địa điểm"} · ${salary}`}
      contentClassName="max-w-3xl"
    >
      {typeof job.match_score === "number" ? (
        <div className="mb-6 rounded-2xl border border-blue-200 bg-blue-50 p-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-blue-700">Mức độ phù hợp với CV chính</p>
              <p className="mt-1 text-3xl font-bold text-blue-700">{Math.round(job.match_score)}%</p>
            </div>
            <div className="h-3 min-w-32 flex-1 overflow-hidden rounded-full bg-blue-100">
              <div
                className="h-full rounded-full bg-gradient-to-r from-blue-500 to-indigo-600"
                style={{ width: `${Math.max(0, Math.min(100, job.match_score))}%` }}
              />
            </div>
          </div>
          {job.matched_skills?.length ? (
            <p className="mt-3 text-sm text-blue-800">Kỹ năng đã khớp: {job.matched_skills.join(", ")}</p>
          ) : null}
          {job.missing_skills?.length ? (
            <p className="mt-1 text-sm text-slate-600">Nên bổ sung: {job.missing_skills.join(", ")}</p>
          ) : null}
        </div>
      ) : null}

      <div className="grid gap-5 text-sm leading-6">
        <JobDetailSection title="Mô tả công việc" value={job.description} />
        <JobDetailSection title="Yêu cầu" value={job.requirements} />
        <JobDetailSection title="Trách nhiệm" value={job.responsibilities} />
        <JobDetailSection title="Quyền lợi" value={job.benefits_text} />
        {job.skills?.length ? (
          <div>
            <h4 className="mb-2 font-semibold">Kỹ năng</h4>
            <div className="flex flex-wrap gap-2">
              {job.skills.map((skill) => <Badge key={skill} tone="blue">{skill}</Badge>)}
            </div>
          </div>
        ) : null}
      </div>

      <div className="mt-7 flex flex-wrap justify-end gap-2 border-t pt-5">
        <Button variant="outline" onClick={() => onBookmark(job)} disabled={working}>
          <BookmarkSimple className="size-4" />Lưu việc làm
        </Button>
        <Button variant="outline" onClick={() => onInterview(job)} disabled={working}>
          <ChatCircleText className="size-4" />Phỏng vấn thử
        </Button>
        <Button onClick={() => onApply(job)} disabled={working}>
          {working ? <SpinnerGap className="size-4 animate-spin" /> : <CheckCircle className="size-4" />}
          Ứng tuyển
        </Button>
      </div>
    </Modal>
  );
}

function JobDetailSection({ title, value }: { title: string; value?: string | null }) {
  if (!value) return null;
  return (
    <div>
      <h4 className="mb-1 font-semibold">{title}</h4>
      <p className="whitespace-pre-line text-muted">{value}</p>
    </div>
  );
}

function PartnerJobWorkspace({
  jobs,
  selectedJob,
  analysisDraft,
  loading,
  workingId,
  schedules,
  scheduleClock,
  scheduleLoading,
  applications,
  applicationsLoading,
  detailTab,
  hasUnsavedChanges,
  query,
  status,
  onQueryChange,
  onStatusChange,
  onCreate,
  onSelect,
  onAnalysisDraftChange,
  onDetailTabChange,
  onSave,
  onManualAction,
  onCreateSchedule,
  onCancelSchedule,
  onUpdateApplicationStatus,
}: {
  jobs: Job[];
  selectedJob: Job | null;
  analysisDraft: JobAnalysisDraft;
  loading: boolean;
  workingId: string | null;
  schedules: JobSchedule[];
  scheduleClock: JobScheduleClock | null;
  scheduleLoading: boolean;
  applications: JobApplication[];
  applicationsLoading: boolean;
  detailTab: PartnerJobTab;
  hasUnsavedChanges: boolean;
  query: string;
  status: string;
  onQueryChange: (value: string) => void;
  onStatusChange: (value: string) => void;
  onCreate: () => void;
  onSelect: (job: Job) => void;
  onAnalysisDraftChange: (draft: JobAnalysisDraft) => void;
  onDetailTabChange: (tab: PartnerJobTab) => void;
  onSave: (job: Job) => void;
  onManualAction: (job: Job, action: JobScheduleAction) => void;
  onCreateSchedule: (
    job: Job,
    action: JobScheduleAction,
    localDateTime: string,
  ) => void;
  onCancelSchedule: (job: Job, scheduleId: string) => void;
  onUpdateApplicationStatus: (job: Job, applicationId: string, newStatus: string) => void;
}) {
  const { dictionary } = useI18n();
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
                  </div>
                  <p className="mt-2 text-xs text-muted">
                    {selectedJob.location_address || dictionary.common.unknown}
                  </p>
                </div>
                {detailTab === "content" ? (
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => onSave(selectedJob)}
                    disabled={workingId === selectedJob.id || !hasUnsavedChanges}
                  >
                    {workingId === selectedJob.id ? (
                      <SpinnerGap className="size-4 animate-spin" />
                    ) : (
                      <FloppyDisk className="size-4" />
                    )}
                    Lưu thay đổi
                  </Button>
                ) : null}
              </div>

              <div className="mt-4 flex flex-wrap gap-2 border-b pb-3">
                {[
                  ["content", "Nội dung"],
                  ["schedule", "Lịch & trạng thái"],
                  ["applications", `Ứng viên (${applications.length})`],
                ].map(([tab, label]) => (
                  <Button
                    key={tab}
                    type="button"
                    variant={detailTab === tab ? "default" : "outline"}
                    size="sm"
                    onClick={() => onDetailTabChange(tab as PartnerJobTab)}
                  >
                    {label}
                  </Button>
                ))}
              </div>

              <div className="relative">
                {detailTab === "content" ? (
                  <JobAnalysisFields
                    draft={analysisDraft}
                    onChange={onAnalysisDraftChange}
                    disabled={workingId === selectedJob.id}
                    className="mt-4"
                  />
                ) : null}
                {detailTab === "schedule" ? (
                  <JobSchedulePanel
                    job={selectedJob}
                    schedules={schedules}
                    clock={scheduleClock}
                    loading={scheduleLoading}
                    disabled={workingId === selectedJob.id}
                    onManualAction={onManualAction}
                    onCreate={onCreateSchedule}
                    onCancel={onCancelSchedule}
                  />
                ) : null}
                {detailTab === "applications" ? (
                  <JobApplicationsPanel
                    job={selectedJob}
                    applications={applications}
                    loading={applicationsLoading}
                    disabled={workingId === selectedJob.id}
                    onUpdateStatus={onUpdateApplicationStatus}
                  />
                ) : null}
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

type JobScheduleAction = "PUBLISH" | "OPEN" | "CLOSE";

type PartnerJobTab = "content" | "schedule" | "applications";

type JobSchedule = {
  id: string;
  job_id: string;
  action: JobScheduleAction;
  run_at: string;
  status: string;
  requested_by: string | null;
  executed_at: string | null;
  error_message: string | null;
};

type JobScheduleClock = {
  timezone: string;
  now: string;
};

type SkillDraft = {
  name: string;
  proficiency: string;
  evidence: string;
};

type JobAnalysisDraft = {
  title: string;
  description: string;
  location: string;
  requiredSkills: SkillDraft[];
  niceToHaveSkills: SkillDraft[];
  responsibilities: string[];
  seniority: string;
  employmentType: string;
  complianceFlags: string[];
  confidence: number;
};

function emptyJobAnalysisDraft(): JobAnalysisDraft {
  return {
    title: "",
    description: "",
    location: "",
    requiredSkills: [],
    niceToHaveSkills: [],
    responsibilities: [],
    seniority: "unknown",
    employmentType: "",
    complianceFlags: [],
    confidence: 0,
  };
}

function analysisDraftFromParsed(parsed: Record<string, unknown> | null | undefined): JobAnalysisDraft {
  if (!parsed) return emptyJobAnalysisDraft();
  return {
    title: String(parsed.title || ""),
    description: String(parsed.description || ""),
    location: String(parsed.location || ""),
    requiredSkills: skillDraftsFromValue(parsed.required_skills),
    niceToHaveSkills: skillDraftsFromValue(parsed.nice_to_have_skills),
    responsibilities: stringListFromValue(parsed.responsibilities),
    seniority: String(parsed.seniority || "unknown"),
    employmentType: String(parsed.employment_type || ""),
    complianceFlags: stringListFromValue(parsed.compliance_flags),
    confidence: typeof parsed.confidence === "number" ? parsed.confidence : 0,
  };
}

function analysisDraftFromJob(job: Job): JobAnalysisDraft {
  return {
    ...analysisDraftFromParsed(job.parsed_requirements),
    title: job.title,
  };
}

function parsedRequirementsFromDraft(draft: JobAnalysisDraft) {
  return {
    document_type: "job_description",
    title: draft.title.trim(),
    description: draft.description.trim(),
    location: draft.location.trim(),
    required_skills: cleanSkillDrafts(draft.requiredSkills),
    nice_to_have_skills: cleanSkillDrafts(draft.niceToHaveSkills),
    responsibilities: cleanLines(draft.responsibilities),
    seniority: draft.seniority || "unknown",
    employment_type: draft.employmentType.trim(),
    compliance_flags: cleanLines(draft.complianceFlags),
    confidence: draft.confidence || 0,
  };
}

function serializeAnalysisDraft(draft: JobAnalysisDraft) {
  return JSON.stringify(parsedRequirementsFromDraft(draft));
}

function requirementsTextFromDraft(draft: JobAnalysisDraft) {
  return cleanSkillDrafts(draft.requiredSkills)
    .map((skill) => [skill.name, skill.proficiency, skill.evidence].filter(Boolean).join(" | "))
    .join("\n");
}

function skillsFromDraft(draft: JobAnalysisDraft) {
  const skills = [...cleanSkillDrafts(draft.requiredSkills), ...cleanSkillDrafts(draft.niceToHaveSkills)]
    .map((skill) => skill.name);
  return Array.from(new Set(skills));
}

function linesToText(lines: string[]) {
  return cleanLines(lines).join("\n");
}

function cleanSkillDrafts(skills: SkillDraft[]) {
  return skills
    .map((skill) => ({
      name: skill.name.trim(),
      proficiency: skill.proficiency || "unknown",
      evidence: skill.evidence.trim(),
    }))
    .filter((skill) => skill.name);
}

function cleanLines(lines: string[]) {
  return lines.map((line) => line.trim()).filter(Boolean);
}

function skillDraftsFromValue(value: unknown): SkillDraft[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (typeof item === "string") {
        return { name: item, proficiency: "unknown", evidence: "" };
      }
      if (item && typeof item === "object") {
        const record = item as Record<string, unknown>;
        return {
          name: String(record.name || ""),
          proficiency: String(record.proficiency || "unknown"),
          evidence: String(record.evidence || ""),
        };
      }
      return { name: "", proficiency: "unknown", evidence: "" };
    })
    .filter((skill) => skill.name.trim());
}

function stringListFromValue(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item || "")).filter((item) => item.trim());
}

function analysisDraftToDescription(draft: JobAnalysisDraft) {
  if (draft.description.trim()) return draft.description.trim();
  return [
    draft.title ? `# ${draft.title}` : "",
    draft.responsibilities.length
      ? `## Responsibilities\n${draft.responsibilities.map((item) => `- ${item}`).join("\n")}`
      : "",
    draft.requiredSkills.length
      ? `## Requirements\n${cleanSkillDrafts(draft.requiredSkills).map((skill) => `- ${skill.name}${skill.evidence ? `: ${skill.evidence}` : ""}`).join("\n")}`
      : "",
    draft.niceToHaveSkills.length
      ? `## Nice to have\n${cleanSkillDrafts(draft.niceToHaveSkills).map((skill) => `- ${skill.name}`).join("\n")}`
      : "",
  ]
    .filter(Boolean)
    .join("\n\n");
}

function backendLocalDateTime(value: string) {
  return value;
}

function formatBackendDateTime(value: string, timezone?: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone,
  }).format(date);
}

function formatScheduleClock(clock: JobScheduleClock) {
  return `${formatBackendDateTime(clock.now, clock.timezone)} (${clock.timezone})`;
}

function scheduleActionLabel(action: JobScheduleAction) {
  if (action === "PUBLISH") return "Đăng job";
  if (action === "OPEN") return "Mở job";
  return "Đóng job";
}

function nextApplicationStatuses(status: string) {
  const transitions: Record<string, string[]> = {
    APPLIED: ["SHORTLISTED", "REJECTED"],
    SHORTLISTED: ["HR_INTERVIEW", "REJECTED"],
    HR_INTERVIEW: ["TECH_INTERVIEW", "FINAL_INTERVIEW", "OFFERED", "REJECTED"],
    TECH_INTERVIEW: ["FINAL_INTERVIEW", "OFFERED", "REJECTED"],
    FINAL_INTERVIEW: ["OFFERED", "REJECTED"],
    OFFERED: ["HIRED", "DECLINED", "REJECTED"],
    HIRED: [],
    REJECTED: [],
    DECLINED: [],
  };
  return transitions[status] || [];
}

function applicationStatusLabel(status: string) {
  const labels: Record<string, string> = {
    SHORTLISTED: "Shortlist",
    HR_INTERVIEW: "HR interview",
    TECH_INTERVIEW: "Tech interview",
    FINAL_INTERVIEW: "Final interview",
    OFFERED: "Offer",
    HIRED: "Hire",
    DECLINED: "Decline",
    REJECTED: "Reject",
  };
  return labels[status] || status;
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

function JobSchedulePanel({
  job,
  schedules,
  clock,
  loading,
  disabled,
  onManualAction,
  onCreate,
  onCancel,
}: {
  job: Job;
  schedules: JobSchedule[];
  clock: JobScheduleClock | null;
  loading: boolean;
  disabled: boolean;
  onManualAction: (job: Job, action: JobScheduleAction) => void;
  onCreate: (job: Job, action: JobScheduleAction, localDateTime: string) => void;
  onCancel: (job: Job, scheduleId: string) => void;
}) {
  const [action, setAction] = useState<JobScheduleAction>("PUBLISH");
  const [localDateTime, setLocalDateTime] = useState("");

  return (
    <div className="mt-4 rounded-xl border bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <h4 className="text-sm font-semibold">Lịch tự động</h4>
        {loading ? <SpinnerGap className="size-4 animate-spin text-primary" /> : null}
      </div>
      <p className="mt-1 text-xs text-muted">
        Giờ backend: {clock ? formatScheduleClock(clock) : "Đang đọc"}
      </p>
      <div className="mt-4 rounded-xl border bg-slate-50 p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h5 className="text-sm font-semibold">Thao tác thủ công</h5>
            <p className="mt-1 text-xs text-muted">
              Áp dụng ngay trạng thái cho job này, không cần chờ lịch.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={disabled}
              onClick={() => onManualAction(job, "PUBLISH")}
            >
              Đăng ngay
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={disabled || job.is_active}
              onClick={() => onManualAction(job, "OPEN")}
            >
              Mở ngay
            </Button>
            <Button
              type="button"
              size="sm"
              variant="danger"
              disabled={disabled || (!job.is_active && job.status === "CLOSED")}
              onClick={() => onManualAction(job, "CLOSE")}
            >
              Đóng ngay
            </Button>
          </div>
        </div>
      </div>
      <div className="mt-4 rounded-xl border bg-white p-4">
        <h5 className="text-sm font-semibold">Đặt lịch tự động</h5>
        <div className="mt-3 grid gap-3 md:grid-cols-[220px_minmax(260px,1fr)_auto] md:items-center">
        <select
          value={action}
          onChange={(event) => setAction(event.target.value as JobScheduleAction)}
          className="focus-ring h-10 w-full rounded-xl border bg-white px-3 text-sm"
          disabled={disabled}
        >
          <option value="PUBLISH">Tự động đăng</option>
          <option value="OPEN">Tự động mở</option>
          <option value="CLOSE">Tự động đóng</option>
        </select>
        <Input
          type="datetime-local"
          value={localDateTime}
          onChange={(event) => setLocalDateTime(event.target.value)}
          disabled={disabled}
        />
        <Button
          type="button"
          variant="outline"
          onClick={() => onCreate(job, action, localDateTime)}
          disabled={disabled || !localDateTime}
        >
          <CalendarBlank className="size-4" />
          Lưu lịch
        </Button>
      </div>
      </div>
      <div className="mt-4 space-y-2">
        {schedules.map((item) => (
          <div key={item.id} className="rounded-lg border bg-slate-50 p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={item.status === "PENDING" ? "amber" : "gray"}>
                    {scheduleActionLabel(item.action)}
                  </Badge>
                  <span className="text-xs font-semibold text-slate-700">{item.status}</span>
                </div>
                <p className="mt-1 text-xs text-muted">
                  {formatBackendDateTime(item.run_at, clock?.timezone)}
                </p>
                {item.error_message ? (
                  <p className="mt-1 text-xs text-red-600">{item.error_message}</p>
                ) : null}
              </div>
              {item.status === "PENDING" ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => onCancel(job, item.id)}
                  disabled={disabled}
                  aria-label="Hủy lịch"
                >
                  <XCircle className="size-4" />
                </Button>
              ) : null}
            </div>
          </div>
        ))}
        {!schedules.length && !loading ? (
          <p className="rounded-lg bg-slate-50 p-3 text-xs text-muted">Chưa có lịch tự động.</p>
        ) : null}
      </div>
    </div>
  );
}

function JobApplicationsPanel({
  job,
  applications,
  loading,
  disabled,
  onUpdateStatus,
}: {
  job: Job;
  applications: JobApplication[];
  loading: boolean;
  disabled: boolean;
  onUpdateStatus: (job: Job, applicationId: string, newStatus: string) => void;
}) {
  return (
    <section className="mt-5 rounded-xl border bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <h4 className="text-sm font-semibold">Ứng viên</h4>
        {loading ? (
          <SpinnerGap className="size-4 animate-spin text-primary" />
        ) : (
          <Badge tone="blue">{applications.length}</Badge>
        )}
      </div>
      <div className="mt-4 space-y-3">
        {applications.map((application) => {
          const nextStatuses = nextApplicationStatuses(application.status);
          return (
            <article key={application.id} className="rounded-xl border bg-slate-50 p-3">
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="gray">{application.status}</Badge>
                    {typeof application.ai_match_score === "number" ? (
                      <Badge tone="green">
                        Match {Math.round(application.ai_match_score * 100)}%
                      </Badge>
                    ) : null}
                    {application.consent_to_unmask ? (
                      <Badge tone="blue">Đã đồng ý mở thông tin</Badge>
                    ) : null}
                  </div>
                  <p className="mt-2 text-xs text-muted">
                    CV {application.cv_id} · Student {application.student_id}
                  </p>
                  {application.cover_letter ? (
                    <p className="mt-2 line-clamp-2 text-sm text-slate-700">
                      {application.cover_letter}
                    </p>
                  ) : null}
                </div>
                <div className="flex flex-wrap gap-2">
                  {nextStatuses.map((status) => (
                    <Button
                      key={status}
                      type="button"
                      variant={status === "REJECTED" ? "danger" : "outline"}
                      size="sm"
                      disabled={disabled}
                      onClick={() => onUpdateStatus(job, application.id, status)}
                    >
                      {applicationStatusLabel(status)}
                    </Button>
                  ))}
                </div>
              </div>
            </article>
          );
        })}
        {!applications.length && !loading ? (
          <p className="rounded-lg bg-slate-50 p-3 text-sm text-muted">
            Chưa có ứng viên ứng tuyển job này.
          </p>
        ) : null}
      </div>
    </section>
  );
}

function JobAnalysisFields({
  draft,
  onChange,
  disabled = false,
  className = "mt-4",
  title = "Dữ liệu phân tích",
  titleFieldLabel = "Tên công việc",
}: {
  draft: JobAnalysisDraft;
  onChange: (draft: JobAnalysisDraft) => void;
  disabled?: boolean;
  className?: string;
  title?: string;
  titleFieldLabel?: string;
}) {
  return (
    <div className={`rounded-xl border bg-white p-4 ${className}`}>
      <div className="flex items-center justify-between gap-3">
        <h4 className="text-sm font-semibold">{title}</h4>
        <Badge tone="blue">{Math.round((draft.confidence || 0) * 100)}%</Badge>
      </div>
      <div className="mt-4 space-y-4">
        <Field label={titleFieldLabel}>
          <Input
            value={draft.title}
            onChange={(event) => onChange({ ...draft, title: event.target.value })}
            disabled={disabled}
          />
        </Field>
        <Field label="Địa điểm">
          <Input
            value={draft.location}
            onChange={(event) => onChange({ ...draft, location: event.target.value })}
            disabled={disabled}
          />
        </Field>
        <Field label="Mô tả">
          <textarea
            value={draft.description}
            onChange={(event) => onChange({ ...draft, description: event.target.value })}
            disabled={disabled}
            className="focus-ring min-h-32 w-full rounded-xl border p-3 text-sm"
          />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
          <Field label="Cấp độ kinh nghiệm">
            <select
              value={draft.seniority}
              onChange={(event) => onChange({ ...draft, seniority: event.target.value })}
              disabled={disabled}
              className="focus-ring h-10 w-full rounded-xl border bg-white px-3 text-sm"
            >
              {[
                ["unknown", "Chưa xác định"],
                ["intern", "Thực tập sinh"],
                ["junior", "Nhân viên mới"],
                ["mid", "Nhân viên có kinh nghiệm"],
                ["senior", "Chuyên viên cao cấp"],
                ["lead", "Trưởng nhóm"],
              ].map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Hình thức làm việc">
            <Input
              value={draft.employmentType}
              onChange={(event) => onChange({ ...draft, employmentType: event.target.value })}
              disabled={disabled}
            />
          </Field>
        </div>
        <SkillTextarea
          label="Kỹ năng bắt buộc"
          skills={draft.requiredSkills}
          disabled={disabled}
          onChange={(requiredSkills) => onChange({ ...draft, requiredSkills })}
        />
        <SkillTextarea
          label="Kỹ năng ưu tiên"
          skills={draft.niceToHaveSkills}
          disabled={disabled}
          onChange={(niceToHaveSkills) => onChange({ ...draft, niceToHaveSkills })}
        />
        <LinesTextarea
          label="Trách nhiệm công việc"
          lines={draft.responsibilities}
          disabled={disabled}
          onChange={(responsibilities) => onChange({ ...draft, responsibilities })}
        />
        <LinesTextarea
          label="Lưu ý tuân thủ"
          lines={draft.complianceFlags}
          disabled={disabled}
          onChange={(complianceFlags) => onChange({ ...draft, complianceFlags })}
        />
      </div>
    </div>
  );
}

function SkillTextarea({
  label,
  skills,
  onChange,
  disabled,
}: {
  label: string;
  skills: SkillDraft[];
  onChange: (skills: SkillDraft[]) => void;
  disabled?: boolean;
}) {
  return (
    <Field label={label}>
      <textarea
        value={skills
          .map((skill) => [skill.name, skill.proficiency, skill.evidence].filter(Boolean).join(" | "))
          .join("\n")}
        onChange={(event) => onChange(parseSkillTextarea(event.target.value))}
        disabled={disabled}
        className="focus-ring min-h-28 w-full rounded-xl border p-3 text-sm"
      />
    </Field>
  );
}

function LinesTextarea({
  label,
  lines,
  onChange,
  disabled,
}: {
  label: string;
  lines: string[];
  onChange: (lines: string[]) => void;
  disabled?: boolean;
}) {
  return (
    <Field label={label}>
      <textarea
        value={lines.join("\n")}
        onChange={(event) => onChange(event.target.value.split(/\r?\n/))}
        disabled={disabled}
        className="focus-ring min-h-24 w-full rounded-xl border p-3 text-sm"
      />
    </Field>
  );
}

function parseSkillTextarea(value: string): SkillDraft[] {
  return value.split(/\r?\n/).map((line) => {
    const [name = "", proficiency = "unknown", evidence = ""] = line.split("|").map((part) => part.trim());
    return { name, proficiency: proficiency || "unknown", evidence };
  });
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
  const [analyzing, setAnalyzing] = useState(false);
  const [draft, setDraft] = useState<JobAnalysisDraft>(() => emptyJobAnalysisDraft());
  const [fileName, setFileName] = useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedDescription = analysisDraftToDescription(draft);
    if (!draft.title.trim() || trimmedDescription.length < 20) {
      toast.error(dictionary.forms.required);
      return;
    }
    setPending(true);
    try {
      await apiFetch("/jobs", {
        method: "POST",
        body: JSON.stringify({
          title: draft.title.trim(),
          description: trimmedDescription,
          requirements: requirementsTextFromDraft(draft),
          responsibilities: linesToText(draft.responsibilities),
          location_address: draft.location.trim(),
          job_type: "INTERNSHIP",
          location_type: "HYBRID",
          skills: skillsFromDraft(draft),
          parsed_requirements: parsedRequirementsFromDraft(draft),
        }),
      });
      await onCreated();
      onOpenChange(false);
      setDraft(emptyJobAnalysisDraft());
      setFileName("");
      toast.success(dictionary.common.updated);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setPending(false);
    }
  }

  async function analyzeUpload(file: File | null) {
    if (!file) return;
    const form = new FormData();
    form.set("file", file);
    setFileName(file.name);
    setAnalyzing(true);
    try {
      const parsed = await apiFetch<Record<string, unknown>>("/jobs/analyze-upload", {
        method: "POST",
        body: form,
      });
      const nextDraft = analysisDraftFromParsed(parsed);
      setDraft(nextDraft);
      toast.success(dictionary.ai.completed);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.ai.failed));
    } finally {
      setAnalyzing(false);
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={dictionary.jobs.create}
      description={dictionary.operations.partner.jobsDescription}
      contentClassName="max-w-5xl"
    >
      <form onSubmit={submit} className="space-y-5">
        <div className="rounded-xl border border-dashed border-blue-200 bg-blue-50/50 p-4">
          <label className="flex cursor-pointer flex-col items-center justify-center gap-2 text-center text-sm font-semibold text-slate-700">
            {analyzing ? (
              <SpinnerGap className="size-5 animate-spin text-primary" />
            ) : (
              <UploadSimple className="size-5 text-primary" />
            )}
            {analyzing
              ? "Đang phân tích tệp PDF"
              : "Tải lên PDF mô tả công việc để AI phân tích"}
            <input
              type="file"
              accept=".pdf,application/pdf"
              className="hidden"
              disabled={analyzing || pending}
              onChange={(event) => void analyzeUpload(event.target.files?.[0] || null)}
            />
          </label>
          <p className="mt-2 truncate text-center text-xs text-muted">
            {fileName || "Chưa chọn tệp PDF"}
          </p>
        </div>
        <JobAnalysisFields
          draft={draft}
          onChange={setDraft}
          disabled={analyzing || pending}
          className=""
          title="Dữ liệu đăng tuyển"
          titleFieldLabel="Tên công việc"
        />
        <Button type="submit" className="w-full" disabled={pending || analyzing}>
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
