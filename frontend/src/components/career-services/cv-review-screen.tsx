"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileMagnifyingGlass, PlusCircle, UserPlus } from "@phosphor-icons/react";
import {
  Button,
  DataTable,
  Input,
  Modal,
  Select,
  StatusBadge,
  Textarea,
  useToast,
  type Column,
} from "@/components/ui";
import { CareerServicesShell } from "./career-services-shell";
import { CareerServicesPermissionGate } from "./permission-gate";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import {
  ApiError,
  CV_REVIEW_PRIORITIES,
  careerServicesApi,
  type CvReviewItem,
  type CvReviewPriority,
  type CvReviewStatus,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

const PRIORITY_TONE: Record<CvReviewPriority, "closed" | "pending" | "active" | "rejected"> = {
  low: "closed",
  normal: "pending",
  high: "active",
  urgent: "rejected",
};

const STATUS_TONE: Record<CvReviewStatus, "pending" | "active" | "rejected" | "accepted" | "closed"> = {
  queued: "pending",
  in_review: "active",
  changes_requested: "rejected",
  approved: "accepted",
  closed: "closed",
};

const NEXT_STATUS: Record<CvReviewStatus, CvReviewStatus[]> = {
  queued: ["in_review"],
  in_review: ["changes_requested", "approved"],
  changes_requested: ["in_review", "closed"],
  approved: ["closed"],
  closed: [],
};

export function CvReviewScreen() {
  const t = useTranslations("careerServices");
  const locale = useLocale();
  const toast = useToast();
  const getErrorMessage = useApiErrorMessage();
  const qc = useQueryClient();

  const [statusFilter, setStatusFilter] = useState<CvReviewStatus | "">("");
  const [createOpen, setCreateOpen] = useState(false);
  const [studentId, setStudentId] = useState("");
  const [cvId, setCvId] = useState("");
  const [priority, setPriority] = useState<CvReviewPriority>("normal");

  const [assignTarget, setAssignTarget] = useState<CvReviewItem | null>(null);
  const [counselorId, setCounselorId] = useState("");

  const [statusTarget, setStatusTarget] = useState<{ item: CvReviewItem; next: CvReviewStatus } | null>(
    null,
  );
  const [feedback, setFeedback] = useState("");

  const query = useQuery({
    queryKey: ["career-services", "cv-review-items", locale, statusFilter],
    queryFn: () => careerServicesApi.listCvReviewItems(locale, { status: statusFilter }),
    retry: false,
  });

  const refresh = () =>
    qc.invalidateQueries({ queryKey: ["career-services", "cv-review-items"] });

  const create = useMutation({
    mutationFn: () =>
      careerServicesApi.createCvReviewItem(
        { student_id: studentId.trim(), cv_id: cvId.trim() || null, priority },
        locale,
      ),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("cvReview.createdToast") });
      setCreateOpen(false);
      setStudentId("");
      setCvId("");
      refresh();
    },
    onError: (error) => toast.show({ tone: "error", title: getErrorMessage(error) }),
  });

  const assign = useMutation({
    mutationFn: () => careerServicesApi.assignCvReview(assignTarget!.id, counselorId.trim(), locale),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("cvReview.assignedToast") });
      setAssignTarget(null);
      setCounselorId("");
      refresh();
    },
    onError: (error) => toast.show({ tone: "error", title: getErrorMessage(error) }),
  });

  const updateStatus = useMutation({
    mutationFn: () =>
      careerServicesApi.updateCvReviewStatus(
        statusTarget!.item.id,
        { status: statusTarget!.next, feedback: feedback.trim() || null },
        locale,
      ),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("cvReview.updatedToast") });
      setStatusTarget(null);
      setFeedback("");
      refresh();
    },
    onError: (error) => toast.show({ tone: "error", title: getErrorMessage(error) }),
  });

  const items = useMemo(() => query.data ?? [], [query.data]);
  const permissionState =
    query.isError && query.error instanceof ApiError ? (
      <CareerServicesPermissionGate error={query.error} bodyOverride={t("cvReview.permissionBody")} />
    ) : null;

  const columns: Column<CvReviewItem>[] = [
    {
      key: "student",
      header: t("cvReview.colStudent"),
      cell: (r) => <span className="font-mono text-xs">{r.student_id}</span>,
    },
    {
      key: "priority",
      header: t("cvReview.colPriority"),
      cell: (r) => <StatusBadge tone={PRIORITY_TONE[r.priority]}>{r.priority_label}</StatusBadge>,
    },
    {
      key: "status",
      header: t("cvReview.colStatus"),
      cell: (r) => <StatusBadge tone={STATUS_TONE[r.status]}>{r.status_label}</StatusBadge>,
    },
    {
      key: "counselor",
      header: t("cvReview.colCounselor"),
      cell: (r) =>
        r.assigned_counselor_id ? (
          <span className="font-mono text-xs">{r.assigned_counselor_id}</span>
        ) : (
          <span className="text-xs text-[var(--text-muted)]">{t("cvReview.unassigned")}</span>
        ),
    },
    {
      key: "created",
      header: t("cvReview.colCreated"),
      cell: (r) => <span className="text-xs text-[var(--text-secondary)]">{formatDateTime(r.created_at, locale)}</span>,
    },
    {
      key: "actions",
      header: t("cvReview.colActions"),
      cell: (r) => (
        <div className="flex flex-wrap gap-1.5">
          <Button variant="ghost" size="xs" onClick={() => setAssignTarget(r)}>
            <UserPlus aria-hidden weight="bold" className="size-4" />
            {t("cvReview.assign")}
          </Button>
          {NEXT_STATUS[r.status].map((next) => (
            <Button
              key={next}
              variant="ghost"
              size="xs"
              onClick={() => setStatusTarget({ item: r, next })}
            >
              {t(`cvReviewStatus.${next}`)}
            </Button>
          ))}
        </div>
      ),
    },
  ];

  return (
    <CareerServicesShell
      title={t("cvReview.title")}
      description={t("cvReview.subtitle")}
      actions={
        !permissionState && (
          <div className="flex items-center gap-2">
            <Select
              aria-label={t("cvReview.filterStatus")}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as CvReviewStatus | "")}
              options={[
                { value: "", label: t("cvReview.allStatuses") },
                { value: "queued", label: t("cvReviewStatus.queued") },
                { value: "in_review", label: t("cvReviewStatus.in_review") },
                { value: "changes_requested", label: t("cvReviewStatus.changes_requested") },
                { value: "approved", label: t("cvReviewStatus.approved") },
                { value: "closed", label: t("cvReviewStatus.closed") },
              ]}
            />
            <Button onClick={() => setCreateOpen(true)}>
              <PlusCircle aria-hidden weight="bold" className="size-4" />
              {t("cvReview.queueCv")}
            </Button>
          </div>
        )
      }
    >
      {permissionState ?? (
        <DataTable
          columns={columns}
          rows={items}
          getRowId={(r) => r.id}
          loading={query.isLoading}
          caption={t("cvReview.title")}
          empty={{
            kind: "empty",
            icon: FileMagnifyingGlass,
            title: t("cvReview.emptyTitle"),
            description: t("cvReview.emptyBody"),
          }}
        />
      )}

      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title={t("cvReview.createTitle")}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setCreateOpen(false)} disabled={create.isPending}>
              {t("cancel")}
            </Button>
            <Button loading={create.isPending} disabled={!studentId.trim()} onClick={() => create.mutate()}>
              {t("save")}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label={t("cvReview.studentIdLabel")}
            required
            help={t("cohorts.studentIdHelp")}
            value={studentId}
            onChange={(e) => setStudentId(e.target.value)}
          />
          <Input
            label={t("cvReview.cvIdLabel")}
            help={t("cvReview.cvIdHelp")}
            value={cvId}
            onChange={(e) => setCvId(e.target.value)}
          />
          <Select
            label={t("cvReview.priorityLabel")}
            required
            value={priority}
            onChange={(e) => setPriority(e.target.value as CvReviewPriority)}
            options={CV_REVIEW_PRIORITIES.map((p) => ({ value: p, label: t(`cvReviewPriority.${p}`) }))}
          />
        </div>
      </Modal>

      <Modal
        open={!!assignTarget}
        onClose={() => setAssignTarget(null)}
        title={t("cvReview.assignTitle")}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setAssignTarget(null)} disabled={assign.isPending}>
              {t("cancel")}
            </Button>
            <Button loading={assign.isPending} disabled={!counselorId.trim()} onClick={() => assign.mutate()}>
              {t("save")}
            </Button>
          </>
        }
      >
        <Input
          label={t("cvReview.counselorIdLabel")}
          required
          help={t("cvReview.counselorIdHelp")}
          value={counselorId}
          onChange={(e) => setCounselorId(e.target.value)}
        />
      </Modal>

      <Modal
        open={!!statusTarget}
        onClose={() => setStatusTarget(null)}
        title={statusTarget ? t(`cvReviewStatus.${statusTarget.next}`) : ""}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setStatusTarget(null)} disabled={updateStatus.isPending}>
              {t("cancel")}
            </Button>
            <Button loading={updateStatus.isPending} onClick={() => updateStatus.mutate()}>
              {t("save")}
            </Button>
          </>
        }
      >
        <Textarea
          label={t("cvReview.feedbackLabel")}
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          rows={4}
        />
      </Modal>
    </CareerServicesShell>
  );
}
