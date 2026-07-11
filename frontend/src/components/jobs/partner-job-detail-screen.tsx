"use client";

import * as React from "react";
import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowLeft,
  Eye,
  Kanban,
  Lightbulb,
  ListChecks,
  LogIn,
  Pencil,
  Search,
  Send,
  ShieldAlert,
  Sparkles,
  Trash2,
  Unlock,
  Users,
  XCircle,
} from "lucide-react";
import { Link, useRouter } from "@/i18n/navigation";
import { Button, EmptyState, Modal, Skeleton, useToast } from "@/components/ui";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  KpiRow,
  KpiTile,
  SectionLabel,
  StatusChip,
  type ChipTone,
} from "@/components/kit";
import { PageHeader } from "@/components/layout/page-header";
import { CompetitionBadge } from "./competition-badge";
import { JobForm } from "./job-form";
import { JdQualityPanel } from "./jd-quality-panel";
import { JobPreviewButtons } from "./job-preview-modal";
import { useJobLabels } from "@/lib/jobs/labels";
import { formatSalary, formatLocation } from "@/lib/jobs/format";
import { formatDateTime } from "@/lib/format";
import { ApiError, jobsApi, type JobStatus, type ModerationStatus } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

const nf = new Intl.NumberFormat();

const STATUS_TONE: Record<JobStatus, ChipTone> = {
  draft: "neutral",
  pending_review: "warning",
  active: "success",
  rejected: "danger",
  closed: "neutral",
  expired: "neutral",
};

const MODERATION_CHIP: Record<ModerationStatus, ChipTone> = {
  pending: "warning",
  approved: "success",
  rejected: "danger",
  flagged: "warning",
};

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
      e instanceof ApiError && typeof e.details?.reason === "string" ? e.details.reason : undefined;
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
      className="mb-4 inline-flex items-center gap-1.5 rounded-lg text-sm font-medium text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
    >
      <ArrowLeft aria-hidden className="size-4" strokeWidth={1.8} />
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
            icon={Search}
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
            icon={err.isPermissionError ? ShieldAlert : LogIn}
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
          icon={AlertCircle}
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
  const applyRate =
    job.application_count > 0 && job.view_count > 0
      ? Math.round((job.application_count / job.view_count) * 100)
      : null;

  if (editing) {
    return (
      <>
        {backLink}
        <PageHeader title={t("editTitle")} description={t("editSubtitle")} />
        <Card padded>
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
        </Card>
      </>
    );
  }

  const actions = (
    <div className="flex flex-wrap items-center gap-2">
      {job.status === "active" && (
        <Link href={`/jobs/${job.id}`} target="_blank">
          <Button variant="ghost" size="sm">
            <Eye aria-hidden className="size-4" strokeWidth={1.8} />
            {t("viewLive")}
          </Button>
        </Link>
      )}
      <JobPreviewButtons jobId={job.id} />
      <Link href={`/partner/jobs/${job.id}/applications`}>
        <Button variant="secondary" size="sm">
          <Users aria-hidden className="size-4" strokeWidth={1.8} />
          {t("viewCandidates")}
        </Button>
      </Link>
      <Link href={`/partner/jobs/${job.id}/pipeline`}>
        <Button variant="secondary" size="sm">
          <Kanban aria-hidden className="size-4" strokeWidth={1.8} />
          {t("viewPipeline")}
        </Button>
      </Link>
      {canEdit && (
        <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>
          <Pencil aria-hidden className="size-4" strokeWidth={1.8} />
          {tc("edit")}
        </Button>
      )}
      {canSubmit && (
        <Button variant="primary" size="sm" onClick={() => setConfirm("submit")}>
          <Send aria-hidden className="size-4" strokeWidth={1.8} />
          {t("submitForReview")}
        </Button>
      )}
      {canClose && (
        <Button variant="secondary" size="sm" onClick={() => setConfirm("close")}>
          <XCircle aria-hidden className="size-4" strokeWidth={1.8} />
          {t("closeJob")}
        </Button>
      )}
      {canReopen && (
        <Button variant="secondary" size="sm" onClick={() => setConfirm("reopen")}>
          <Unlock aria-hidden className="size-4" strokeWidth={1.8} />
          {t("reopenJob")}
        </Button>
      )}
      {canDelete && (
        <Button variant="danger" size="sm" onClick={() => setConfirm("delete")}>
          <Trash2 aria-hidden className="size-4" strokeWidth={1.8} />
          {tc("delete")}
        </Button>
      )}
    </div>
  );

  return (
    <>
      {backLink}
      <PageHeader title={job.title} actions={actions} />

      <div className="mb-4 flex flex-wrap items-center gap-1.5">
        <StatusChip tone={STATUS_TONE[job.status] ?? "neutral"} dot>
          {labels.status(job.status, job.status_label)}
        </StatusChip>
        <StatusChip tone={MODERATION_CHIP[job.moderation_status] ?? "neutral"}>
          {t("moderationLabel")}: {labels.moderation(job.moderation_status, job.moderation_status_label)}
        </StatusChip>
        <StatusChip tone="info">
          {t("visibilityLabel")}: {labels.visibility(job.visibility)}
        </StatusChip>
        {job.is_sponsored && <StatusChip tone="amber">{t("sponsored")}</StatusChip>}
      </div>

      {/* Key-metric tiles */}
      <KpiRow cols={3} className="mb-4">
        <KpiTile label={t("applications")} value={nf.format(job.application_count)} icon={Users} />
        <KpiTile label={t("views")} value={nf.format(job.view_count)} icon={Eye} />
        <KpiTile label={t("statApplyRate")} value={applyRate != null ? `${applyRate}%` : "—"} icon={ListChecks} />
      </KpiRow>

      {/* AI job performance insights */}
      {(() => {
        const insights: string[] = [];
        const daysLeft = job.application_deadline
          ? Math.ceil((new Date(job.application_deadline).getTime() - Date.now()) / 86_400_000)
          : null;
        if (job.status === "active") {
          if (job.application_count >= 50) insights.push(t("detailInsightHighInterest", { count: job.application_count }));
          else if (job.application_count === 0) insights.push(t("detailInsightNoApplicants"));
          else if (job.application_count > 0) insights.push(t("detailInsightActive", { count: job.application_count }));
          if (applyRate !== null) insights.push(t("detailInsightApplyRate", { rate: applyRate }));
          if (daysLeft !== null && daysLeft >= 0 && daysLeft <= 5) insights.push(t("detailInsightDeadlineSoon", { days: daysLeft }));
        }
        if (insights.length === 0) return null;
        return (
          <Card className="mb-4 border-l-[3px]" style={{ borderLeftColor: "var(--content-ai)" }}>
            <CardHeader>
              <div className="flex items-center gap-2">
                <span
                  className="flex size-7 items-center justify-center rounded-lg"
                  style={{ background: "var(--content-ai-soft)" }}
                >
                  <Sparkles className="size-4" strokeWidth={1.9} style={{ color: "var(--content-ai)" }} />
                </span>
                <CardTitle>{t("aiPerformanceTitle")}</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {insights.map((s, i) => (
                  <li key={i} className="flex items-start gap-2 text-[0.8125rem] text-foreground">
                    <Lightbulb aria-hidden className="mt-0.5 size-3.5 shrink-0" strokeWidth={1.9} style={{ color: "var(--content-ai)" }} />
                    {s}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        );
      })()}

      {/* JD quality gate — inline before submit */}
      {canSubmit && (
        <div className="mb-4">
          <SectionLabel className="mb-2">{t("quality.sectionTitle")}</SectionLabel>
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
          className="mb-4 rounded-xl p-4"
          style={{ background: "var(--content-danger-soft)" }}
        >
          <p className="text-sm font-semibold" style={{ color: "var(--content-danger)" }}>
            {t("rejectionReasonTitle")}
          </p>
          <p className="mt-1 whitespace-pre-wrap text-sm text-foreground">{job.moderation_note}</p>
          <p className="mt-2 type-caption text-muted-foreground">{t("rejectionHint")}</p>
        </div>
      )}

      {job.status === "pending_review" && (
        <div
          role="status"
          className="mb-4 rounded-xl p-4 text-sm"
          style={{ background: "var(--content-warning-soft)", color: "var(--content-warning)" }}
        >
          {t("pendingReviewHint")}
        </div>
      )}

      {/* Meta + content */}
      <Card padded className="mb-4">
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
          <Meta label={t("employmentType")}>{labels.employmentType(job.employment_type, job.employment_type_label)}</Meta>
          <Meta label={t("locationMode")}>{labels.locationType(job.location_type, job.location_type_label)}</Meta>
          <Meta label={t("location")}>{formatLocation(job.location_city, job.location_country)}</Meta>
          <Meta label={t("salary")}>{salary ?? t("salaryUndisclosed")}</Meta>
          <Meta label={t("headcount")}>{job.headcount}</Meta>
          <Meta label={t("deadline")}>
            {job.application_deadline ? formatDateTime(job.application_deadline, locale) : t("noDeadline")}
          </Meta>
          <Meta label={t("created")}>{formatDateTime(job.created_at, locale)}</Meta>
        </dl>
      </Card>

      <Section title={t("description")}>{job.description}</Section>
      {job.requirements && <Section title={t("requirements")}>{job.requirements}</Section>}
      {job.benefits && <Section title={t("benefits")}>{job.benefits}</Section>}

      {job.required_skills.length > 0 && <SkillBlock title={t("requiredSkills")} skills={job.required_skills} />}
      {job.preferred_skills.length > 0 && <SkillBlock title={t("preferredSkills")} skills={job.preferred_skills} />}

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
            <Button variant="ghost" onClick={() => setConfirm(null)}>{tc("cancel")}</Button>
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
          <p className="text-sm text-muted-foreground">{t("submitConfirmNote")}</p>
          <JdQualityPanel
            issues={qualityQuery.data?.issues ?? []}
            passed={qualityQuery.data?.passed}
            loading={qualityQuery.isPending}
            compact
          />
          {qualityQuery.data?.passed === false && (
            <p className="type-caption font-medium" style={{ color: "var(--content-danger)" }}>
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
            <Button variant="ghost" onClick={() => setConfirm(null)}>{tc("cancel")}</Button>
            <Button variant="primary" loading={close.isPending} onClick={() => close.mutate()}>{t("closeJob")}</Button>
          </>
        }
      >
        <p className="text-sm text-muted-foreground">{t("closeConfirmNote")}</p>
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
            <Button variant="ghost" onClick={() => setConfirm(null)}>{tc("cancel")}</Button>
            <Button variant="primary" loading={reopen.isPending} onClick={() => reopen.mutate()}>{t("reopenJob")}</Button>
          </>
        }
      >
        <p className="text-sm text-muted-foreground">{t("reopenConfirmNote")}</p>
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
            <Button variant="ghost" onClick={() => setConfirm(null)}>{tc("cancel")}</Button>
            <Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>{tc("delete")}</Button>
          </>
        }
      >
        <p className="text-sm text-muted-foreground">{t("deleteConfirmNote")}</p>
      </Modal>
    </>
  );
}

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="type-caption text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-[0.8125rem] font-semibold text-foreground">{children}</dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card padded className="mt-4">
      <h2 className="type-h3 mb-2 text-foreground">{title}</h2>
      <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">{children}</p>
    </Card>
  );
}

function SkillBlock({ title, skills }: { title: string; skills: string[] }) {
  return (
    <Card padded className="mt-4">
      <SectionLabel className="mb-2">{title}</SectionLabel>
      <ul className="flex flex-wrap gap-1.5">
        {skills.map((s) => (
          <li key={s}>
            <StatusChip tone="neutral">{s}</StatusChip>
          </li>
        ))}
      </ul>
    </Card>
  );
}
