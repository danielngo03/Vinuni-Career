"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  PaperPlaneTilt,
  PencilSimple,
  Trash,
  LockSimpleOpen,
  XCircle,
  WarningCircle,
  ShieldWarning,
  SignIn,
  MagnifyingGlass,
  Eye,
  Users,
  Kanban,
  Sparkle,
  LightbulbFilament,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { Link, useRouter } from "@/i18n/navigation";
import {
  Button,
  EmptyState,
  Modal,
  Skeleton,
  StatusBadge,
  SponsoredLabel,
  useToast,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { CompetitionBadge } from "./competition-badge";
import { JobForm } from "./job-form";
import { JdQualityPanel } from "./jd-quality-panel";
import { JobPreviewButtons } from "./job-preview-modal";
import {
  useJobLabels,
  JOB_STATUS_TONE,
  MODERATION_TONE,
} from "@/lib/jobs/labels";
import { formatSalary, formatLocation } from "@/lib/jobs/format";
import { formatDateTime } from "@/lib/format";
import { ApiError, jobsApi } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

type ConfirmKind = "submit" | "delete" | "close" | "reopen" | null;

export function PartnerJobDetailScreen({ jobId }: { jobId: string }) {
  const t = useTranslations("jobs");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useJobLabels();
  const toast = useToast();
  const qc = useQueryClient();
  const router = useRouter();
  const getMessage = useApiErrorMessage();

  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState<ConfirmKind>(null);

  const query = useQuery({
    queryKey: ["jobs", "owned", jobId],
    queryFn: () => jobsApi.getOwned(jobId),
    retry: false,
  });

  const job = query.data;
  const canSubmitStatus = job?.status === "draft" || job?.status === "rejected";

  // JD quality-check rubric (B-552) — only meaningful before submit; fetched
  // whenever the job is in a submittable state so the finding list is visible
  // inline on the page, not just inside the submit confirmation.
  const qualityQuery = useQuery({
    queryKey: ["jobs", "quality-check", jobId],
    queryFn: () => jobsApi.qualityCheck(jobId),
    enabled: canSubmitStatus,
    retry: false,
  });

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["jobs", "owned", jobId] });
    void qc.invalidateQueries({ queryKey: ["jobs", "mine"] });
  }

  function handleError(e: unknown) {
    const reason =
      e instanceof ApiError && typeof e.details?.reason === "string"
        ? e.details.reason
        : undefined;
    if (reason === "version_conflict" || (e instanceof ApiError && e.code === "CONFLICT")) {
      toast.show({ tone: "error", title: t("conflictToast"), description: t("conflictBody") });
      refresh();
      return;
    }
    if (reason === "illegal_transition") {
      toast.show({ tone: "error", title: t("illegalTransitionToast") });
      refresh();
      return;
    }
    if (reason === "jd_quality_check_failed") {
      // Defensive: the inline quality panel should already have blocked this,
      // but the JD may have been edited elsewhere between page load and
      // submit — refetch so the (now stale) findings are current.
      toast.show({ tone: "error", title: t("quality.blockedToast") });
      void qc.invalidateQueries({ queryKey: ["jobs", "quality-check", jobId] });
      return;
    }
    toast.show({ tone: "error", title: getMessage(e) });
  }

  const submit = useMutation({
    mutationFn: () => jobsApi.submit(jobId),
    onSuccess: () => {
      setConfirm(null);
      toast.show({ tone: "success", title: t("submittedToast") });
      refresh();
    },
    onError: handleError,
  });

  const close = useMutation({
    mutationFn: () => jobsApi.close(jobId, job?.version),
    onSuccess: () => {
      setConfirm(null);
      toast.show({ tone: "success", title: t("closedToast") });
      refresh();
    },
    onError: handleError,
  });

  const reopen = useMutation({
    mutationFn: () => jobsApi.reopen(jobId, job?.version),
    onSuccess: () => {
      setConfirm(null);
      toast.show({ tone: "success", title: t("reopenedToast") });
      refresh();
    },
    onError: handleError,
  });

  const remove = useMutation({
    mutationFn: () => jobsApi.remove(jobId),
    onSuccess: () => {
      setConfirm(null);
      toast.show({ tone: "success", title: t("deletedToast") });
      void qc.invalidateQueries({ queryKey: ["jobs", "mine"] });
      router.push("/partner/jobs");
    },
    onError: handleError,
  });

  const backLink = (
    <Link
      href="/partner/jobs"
      className="mb-4 inline-flex items-center gap-1.5 rounded-lg text-sm font-medium text-[var(--text-secondary)] outline-none hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
    >
      <ArrowLeft aria-hidden weight="bold" className="size-4" />
      {t("backToJobs")}
    </Link>
  );

  /* ---- Non-data states ---- */
  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isNotFound) {
      return (
        <>
          {backLink}
          <EmptyState
            kind="empty"
            icon={MagnifyingGlass}
            title={t("notFoundTitle")}
            description={t("ownerNotFoundBody")}
            action={
              <Link href="/partner/jobs">
                <Button variant="secondary">{t("backToJobs")}</Button>
              </Link>
            }
          />
        </>
      );
    }
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          {backLink}
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            icon={err.isPermissionError ? ShieldWarning : SignIn}
            title={err.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")}
            description={err.isPermissionError ? t("permissionBody") : tStates("authBody")}
          />
        </>
      );
    }
    return (
      <>
        {backLink}
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={tStates("errorTitle")}
          description={tStates("errorBody")}
          action={
            <Button variant="secondary" onClick={() => query.refetch()}>
              {tc("retry")}
            </Button>
          }
        />
      </>
    );
  }

  if (query.isPending || !job) {
    return (
      <>
        {backLink}
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="mt-3 h-4 w-1/3" />
        <Skeleton className="mt-6 h-48 w-full" />
      </>
    );
  }

  const canEdit = job.status === "draft" || job.status === "rejected";
  const canSubmit = job.status === "draft" || job.status === "rejected";
  const canClose = job.status === "active";
  const canReopen = job.status === "closed";
  const canDelete = ["draft", "rejected", "closed", "expired"].includes(job.status);
  const salary = formatSalary(job.salary, locale);

  if (editing) {
    return (
      <>
        {backLink}
        <PageHeader title={t("editTitle")} description={t("editSubtitle")} />
        <div className="rounded-2xl border border-[var(--border-default)] bg-white p-6">
          <JobForm
            mode="edit"
            job={job}
            qualityIssues={canSubmit ? qualityQuery.data?.issues : undefined}
            onSuccess={(updated) => {
              setEditing(false);
              qc.setQueryData(["jobs", "owned", jobId], updated);
              void qc.invalidateQueries({ queryKey: ["jobs", "mine"] });
            }}
            onCancel={() => setEditing(false)}
          />
        </div>
      </>
    );
  }

  const actions = (
    <div className="flex flex-wrap items-center gap-2">
      {job.status === "active" && (
        <Link href={`/jobs/${job.id}`} target="_blank">
          <Button variant="ghost" size="sm">
            <Eye aria-hidden weight="duotone" className="size-4" />
            {t("viewLive")}
          </Button>
        </Link>
      )}
      <JobPreviewButtons jobId={job.id} />
      <Link href={`/partner/jobs/${job.id}/applications`}>
        <Button variant="secondary" size="sm">
          <Users aria-hidden weight="duotone" className="size-4" />
          {t("viewCandidates")}
        </Button>
      </Link>
      <Link href={`/partner/jobs/${job.id}/pipeline`}>
        <Button variant="secondary" size="sm">
          <Kanban aria-hidden weight="duotone" className="size-4" />
          {t("viewPipeline")}
        </Button>
      </Link>
      {canEdit && (
        <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>
          <PencilSimple aria-hidden weight="bold" className="size-4" />
          {tc("edit")}
        </Button>
      )}
      {canSubmit && (
        <Button variant="primary" size="sm" onClick={() => setConfirm("submit")}>
          <PaperPlaneTilt aria-hidden weight="bold" className="size-4" />
          {t("submitForReview")}
        </Button>
      )}
      {canClose && (
        <Button variant="secondary" size="sm" onClick={() => setConfirm("close")}>
          <XCircle aria-hidden weight="bold" className="size-4" />
          {t("closeJob")}
        </Button>
      )}
      {canReopen && (
        <Button variant="secondary" size="sm" onClick={() => setConfirm("reopen")}>
          <LockSimpleOpen aria-hidden weight="bold" className="size-4" />
          {t("reopenJob")}
        </Button>
      )}
      {canDelete && (
        <Button variant="danger" size="sm" onClick={() => setConfirm("delete")}>
          <Trash aria-hidden weight="bold" className="size-4" />
          {tc("delete")}
        </Button>
      )}
    </div>
  );

  return (
    <>
      {backLink}
      <PageHeader title={job.title} actions={actions} />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <StatusBadge tone={JOB_STATUS_TONE[job.status] ?? "info"}>
          {labels.status(job.status, job.status_label)}
        </StatusBadge>
        <StatusBadge tone={MODERATION_TONE[job.moderation_status] ?? "info"}>
          {t("moderationLabel")}: {labels.moderation(job.moderation_status, job.moderation_status_label)}
        </StatusBadge>
        <StatusBadge tone="info">
          {t("visibilityLabel")}: {labels.visibility(job.visibility)}
        </StatusBadge>
        {job.is_sponsored && <SponsoredLabel label={t("sponsored")} />}
      </div>

      {/* Job key-metric tiles */}
      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div className="rounded-2xl border border-[var(--border-default)] bg-white px-4 py-3.5 shadow-[0_2px_12px_rgba(11,34,57,0.06)] transition-all hover:-translate-y-0.5">
          <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-primary shadow-sm">
            <Users aria-hidden weight="duotone" className="size-4.5 text-white" />
          </div>
          <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">{job.application_count}</p>
          <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("applications")}</p>
        </div>
        <div className="rounded-2xl border border-[var(--border-default)] bg-white px-4 py-3.5 shadow-[0_2px_12px_rgba(11,34,57,0.06)] transition-all hover:-translate-y-0.5">
          <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-success shadow-sm">
            <Eye aria-hidden weight="duotone" className="size-4.5 text-white" />
          </div>
          <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">{job.view_count}</p>
          <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("views")}</p>
        </div>
        <div className="rounded-2xl border border-[var(--border-default)] bg-white px-4 py-3.5 shadow-[0_2px_12px_rgba(11,34,57,0.06)] transition-all hover:-translate-y-0.5">
          <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-info shadow-sm">
            <Kanban aria-hidden weight="duotone" className="size-4.5 text-white" />
          </div>
          <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">
            {job.application_count > 0 && job.view_count > 0
              ? `${Math.round((job.application_count / job.view_count) * 100)}%`
              : "—"}
          </p>
          <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("statApplyRate")}</p>
        </div>
      </div>

      {/* AI Job Performance Insights */}
      {(() => {
        const insights: string[] = [];
        const applyRate = job.application_count > 0 && job.view_count > 0
          ? Math.round((job.application_count / job.view_count) * 100)
          : null;
        const daysLeft = job.application_deadline
          ? Math.ceil((new Date(job.application_deadline).getTime() - Date.now()) / 86_400_000)
          : null;

        if (job.status === "active") {
          if (job.application_count >= 50) {
            insights.push(t("detailInsightHighInterest", { count: job.application_count }));
          } else if (job.application_count === 0) {
            insights.push(t("detailInsightNoApplicants"));
          } else if (job.application_count > 0) {
            insights.push(t("detailInsightActive", { count: job.application_count }));
          }
          if (applyRate !== null) {
            insights.push(t("detailInsightApplyRate", { rate: applyRate }));
          }
          if (daysLeft !== null && daysLeft >= 0 && daysLeft <= 5) {
            insights.push(t("detailInsightDeadlineSoon", { days: daysLeft }));
          }
        }

        if (insights.length === 0) return null;
        return (
          <div className={cn(
            "mb-6 rounded-2xl border p-4",
            "border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white/60 ",
          )}>
            <p className="mb-3 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-info shadow-sm">
                <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
              </span>
              {t("aiPerformanceTitle")}
            </p>
            <ul className="space-y-1.5">
              {insights.map((s, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-[var(--text-secondary)]">
                  <LightbulbFilament aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0 text-[var(--ai-accent)]" />
                  {s}
                </li>
              ))}
            </ul>
          </div>
        );
      })()}

      {/* JD quality-check rubric (B-552) — visible inline before the partner
          even opens the submit confirmation, not just as a toast. */}
      {canSubmit && (
        <div className="mb-6">
          <h2 className="mb-2 text-sm font-bold tracking-tight text-[var(--text-primary)]">
            {t("quality.sectionTitle")}
          </h2>
          <JdQualityPanel
            issues={qualityQuery.data?.issues ?? []}
            passed={qualityQuery.data?.passed}
            loading={qualityQuery.isPending}
          />
        </div>
      )}

      {/* Rejection / moderation note */}
      {job.status === "rejected" && job.moderation_note && (
        <div
          role="alert"
          className="mb-6 rounded-2xl border border-[var(--red-400)]/40 bg-[var(--red-50)] p-4"
        >
          <p className="text-sm font-semibold text-[var(--brand-red)]">
            {t("rejectionReasonTitle")}
          </p>
          <p className="mt-1 whitespace-pre-wrap text-sm text-[var(--text-secondary)]">
            {job.moderation_note}
          </p>
          <p className="mt-2 text-xs text-[var(--text-muted)]">{t("rejectionHint")}</p>
        </div>
      )}

      {job.status === "pending_review" && (
        <div
          role="status"
          className="mb-6 rounded-2xl border border-[var(--amber-600)]/40 bg-[var(--amber-100)] p-4 text-sm text-[var(--amber-700)]"
        >
          {t("pendingReviewHint")}
        </div>
      )}

      {/* Meta grid */}
      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Meta label={t("employmentType")}>
          {labels.employmentType(job.employment_type, job.employment_type_label)}
        </Meta>
        <Meta label={t("locationMode")}>
          {labels.locationType(job.location_type, job.location_type_label)}
        </Meta>
        <Meta label={t("location")}>
          {formatLocation(job.location_city, job.location_country)}
        </Meta>
        <Meta label={t("salary")}>{salary ?? t("salaryUndisclosed")}</Meta>
        <Meta label={t("headcount")}>{job.headcount}</Meta>
        <Meta label={t("applications")}>{job.application_count}</Meta>
        <Meta label={t("deadline")}>
          {job.application_deadline
            ? formatDateTime(job.application_deadline, locale)
            : t("noDeadline")}
        </Meta>
        <Meta label={t("created")}>{formatDateTime(job.created_at, locale)}</Meta>
        <Meta label={t("views")}>{job.view_count}</Meta>
      </dl>

      <Section title={t("description")}>{job.description}</Section>
      {job.requirements && <Section title={t("requirements")}>{job.requirements}</Section>}
      {job.benefits && <Section title={t("benefits")}>{job.benefits}</Section>}

      {job.required_skills.length > 0 && (
        <SkillBlock title={t("requiredSkills")} skills={job.required_skills} />
      )}
      {job.preferred_skills.length > 0 && (
        <SkillBlock title={t("preferredSkills")} skills={job.preferred_skills} />
      )}

      {job.screening_questions.length > 0 && (
        <section className="mt-6">
          <h2 className="mb-2 text-lg font-bold tracking-tight text-[var(--text-primary)]">
            {t("screeningQuestions")}
          </h2>
          <ol className="space-y-2">
            {job.screening_questions.map((q) => (
              <li
                key={q.id}
                className="rounded-xl border border-[var(--border-default)] bg-white p-3"
              >
                <p className="text-sm font-medium text-[var(--text-primary)]">
                  {q.question}
                </p>
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  {labels.screeningType(q.q_type)}
                  {" · "}
                  {q.is_required ? t("required") : t("optional")}
                </p>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* Competition signal — shown only when job is active/published */}
      {job.status === "active" && (
        <div className="mt-6">
          <CompetitionBadge jobId={job.id} />
        </div>
      )}

      {/* Confirm modals */}
      <Modal
        open={confirm === "submit"}
        onClose={() => setConfirm(null)}
        title={t("submitConfirmTitle")}
        description={t("submitConfirmBody")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirm(null)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="primary"
              loading={submit.isPending}
              disabled={qualityQuery.data?.passed === false}
              onClick={() => submit.mutate()}
            >
              {t("submitForReview")}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <p className="text-sm text-[var(--text-secondary)]">{t("submitConfirmNote")}</p>
          <JdQualityPanel
            issues={qualityQuery.data?.issues ?? []}
            passed={qualityQuery.data?.passed}
            loading={qualityQuery.isPending}
            compact
          />
          {qualityQuery.data?.passed === false && (
            <p className="text-xs font-medium text-[var(--brand-red)]">
              {t("quality.fixBeforeSubmit")}
            </p>
          )}
        </div>
      </Modal>

      <Modal
        open={confirm === "close"}
        onClose={() => setConfirm(null)}
        title={t("closeConfirmTitle")}
        description={t("closeConfirmBody")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirm(null)}>
              {tc("cancel")}
            </Button>
            <Button variant="primary" loading={close.isPending} onClick={() => close.mutate()}>
              {t("closeJob")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">{t("closeConfirmNote")}</p>
      </Modal>

      <Modal
        open={confirm === "reopen"}
        onClose={() => setConfirm(null)}
        title={t("reopenConfirmTitle")}
        description={t("reopenConfirmBody")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirm(null)}>
              {tc("cancel")}
            </Button>
            <Button variant="primary" loading={reopen.isPending} onClick={() => reopen.mutate()}>
              {t("reopenJob")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">{t("reopenConfirmNote")}</p>
      </Modal>

      <Modal
        open={confirm === "delete"}
        onClose={() => setConfirm(null)}
        title={t("deleteConfirmTitle")}
        description={t("deleteConfirmBody")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirm(null)}>
              {tc("cancel")}
            </Button>
            <Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>
              {tc("delete")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">{t("deleteConfirmNote")}</p>
      </Modal>
    </>
  );
}

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-[var(--border-default)] bg-white px-3.5 py-2.5 ">
      <dt className="text-xs font-medium text-[var(--text-muted)]">{label}</dt>
      <dd className="mt-0.5 text-sm font-semibold text-[var(--text-primary)]">{children}</dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h2 className="mb-2 text-lg font-bold tracking-tight text-[var(--text-primary)]">
        {title}
      </h2>
      <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--text-secondary)]">
        {children}
      </p>
    </section>
  );
}

function SkillBlock({ title, skills }: { title: string; skills: string[] }) {
  return (
    <section className="mt-6">
      <h2 className="mb-2 text-sm font-semibold text-[var(--text-primary)]">{title}</h2>
      <ul className="flex flex-wrap gap-1.5">
        {skills.map((s) => (
          <li
            key={s}
            className="rounded-full bg-[var(--bg-subtle)] px-3 py-1 text-xs font-medium text-[var(--text-secondary)]"
          >
            {s}
          </li>
        ))}
      </ul>
    </section>
  );
}
