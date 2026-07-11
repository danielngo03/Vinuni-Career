"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileSearch, Plus, UserPlus } from "lucide-react";
import { Button, Input, Modal, Select, Textarea, useToast } from "@/components/ui";
import {
  DataTable,
  EmptyState,
  FilterBar,
  StatusChip,
  type ChipTone,
  type ColumnDef,
} from "@/components/kit";
import { cn } from "@/lib/utils";
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

const PRIORITY_TONE: Record<CvReviewPriority, ChipTone> = {
  low: "neutral",
  normal: "info",
  high: "amber",
  urgent: "danger",
};

const STATUS_TONE: Record<CvReviewStatus, ChipTone> = {
  queued: "warning",
  in_review: "info",
  changes_requested: "rose",
  approved: "success",
  closed: "neutral",
};

const NEXT_STATUS: Record<CvReviewStatus, CvReviewStatus[]> = {
  queued: ["in_review"],
  in_review: ["changes_requested", "approved"],
  changes_requested: ["in_review", "closed"],
  approved: ["closed"],
  closed: [],
};

const STATUS_FILTERS: (CvReviewStatus | "")[] = [
  "",
  "queued",
  "in_review",
  "changes_requested",
  "approved",
  "closed",
];

export function CvReviewScreen() {
  const t = useTranslations("careerServices");
  const locale = useLocale();
  const toast = useToast();
  const getErrorMessage = useApiErrorMessage();
  const qc = useQueryClient();

  const [statusFilter, setStatusFilter] = React.useState<CvReviewStatus | "">("");
  const [createOpen, setCreateOpen] = React.useState(false);
  const [studentId, setStudentId] = React.useState("");
  const [cvId, setCvId] = React.useState("");
  const [priority, setPriority] = React.useState<CvReviewPriority>("normal");

  const [assignTarget, setAssignTarget] = React.useState<CvReviewItem | null>(null);
  const [counselorId, setCounselorId] = React.useState("");

  const [statusTarget, setStatusTarget] = React.useState<{ item: CvReviewItem; next: CvReviewStatus } | null>(
    null,
  );
  const [feedback, setFeedback] = React.useState("");

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

  const items = query.data ?? [];
  const permissionState =
    query.isError && query.error instanceof ApiError ? (
      <CareerServicesPermissionGate error={query.error} bodyOverride={t("cvReview.permissionBody")} />
    ) : null;

  const createButton = (
    <Button onClick={() => setCreateOpen(true)} size="sm">
      <Plus className="size-4" strokeWidth={2} />
      {t("cvReview.queueCv")}
    </Button>
  );

  const columns: ColumnDef<CvReviewItem, unknown>[] = [
    {
      accessorKey: "student_id",
      header: t("cvReview.colStudent"),
      cell: ({ row }) => <span className="font-mono text-xs text-foreground">{row.original.student_id}</span>,
    },
    {
      accessorKey: "priority",
      header: t("cvReview.colPriority"),
      cell: ({ row }) => (
        <StatusChip tone={PRIORITY_TONE[row.original.priority]} dot>
          {row.original.priority_label}
        </StatusChip>
      ),
    },
    {
      accessorKey: "status",
      header: t("cvReview.colStatus"),
      cell: ({ row }) => (
        <StatusChip tone={STATUS_TONE[row.original.status]}>{row.original.status_label}</StatusChip>
      ),
    },
    {
      id: "counselor",
      header: t("cvReview.colCounselor"),
      cell: ({ row }) =>
        row.original.assigned_counselor_id ? (
          <span className="font-mono text-xs text-foreground">{row.original.assigned_counselor_id}</span>
        ) : (
          <span className="type-small text-muted-foreground">{t("cvReview.unassigned")}</span>
        ),
    },
    {
      id: "created",
      header: t("cvReview.colCreated"),
      meta: { align: "right" },
      cell: ({ row }) => (
        <span className="type-small tabular-nums text-muted-foreground">
          {formatDateTime(row.original.created_at, locale)}
        </span>
      ),
    },
    {
      id: "actions",
      header: "",
      enableSorting: false,
      meta: { align: "right" },
      cell: ({ row }) => {
        const r = row.original;
        return (
          <div className="flex flex-wrap items-center justify-end gap-1">
            <Button variant="ghost" size="sm" onClick={() => setAssignTarget(r)}>
              <UserPlus className="size-4" strokeWidth={1.8} />
              {t("cvReview.assign")}
            </Button>
            {NEXT_STATUS[r.status].map((next) => (
              <Button key={next} variant="ghost" size="sm" onClick={() => setStatusTarget({ item: r, next })}>
                {t(`cvReviewStatus.${next}`)}
              </Button>
            ))}
          </div>
        );
      },
    },
  ];

  return (
    <CareerServicesShell
      title={t("cvReview.title")}
      description={t("cvReview.subtitle")}
      actions={!permissionState ? createButton : undefined}
    >
      {permissionState ?? (
        <div className="space-y-4">
          <FilterBar>
            <div className="flex flex-wrap gap-1.5" role="group" aria-label={t("cvReview.filterStatus")}>
              {STATUS_FILTERS.map((s) => {
                const active = statusFilter === s;
                return (
                  <button
                    key={s || "all"}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setStatusFilter(s)}
                    className={cn(
                      "inline-flex items-center rounded-full border px-3 py-1 text-[0.8125rem] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]",
                      active
                        ? "border-transparent bg-foreground text-[var(--surface-card)]"
                        : "border-border bg-card text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {s === "" ? t("cvReview.allStatuses") : t(`cvReviewStatus.${s}`)}
                  </button>
                );
              })}
            </div>
          </FilterBar>

          <DataTable
            columns={columns}
            data={items}
            getRowId={(r) => r.id}
            loading={query.isPending}
            empty={
              <EmptyState
                kind="empty"
                icon={FileSearch}
                title={t("cvReview.emptyTitle")}
                description={t("cvReview.emptyBody")}
              />
            }
          />
        </div>
      )}

      {/* Queue a CV */}
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

      {/* Assign counselor */}
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

      {/* Status change + feedback */}
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
