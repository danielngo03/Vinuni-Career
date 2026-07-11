"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Plus, XCircle } from "lucide-react";
import { Button, Input, Modal, Select, Textarea, useToast } from "@/components/ui";
import {
  DataTable,
  DetailSheet,
  DetailSheetSection,
  DetailRow,
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
  RISK_REASONS,
  RISK_SEVERITIES,
  careerServicesApi,
  type AtRiskFlag,
  type RiskReason,
  type RiskSeverity,
  type RiskStatus,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

const SEVERITY_TONE: Record<RiskSeverity, ChipTone> = {
  low: "emerald",
  medium: "amber",
  high: "rose",
};

const STATUS_TONE: Record<RiskStatus, ChipTone> = {
  open: "warning",
  in_progress: "info",
  resolved: "success",
  dismissed: "neutral",
};

const STATUS_FILTERS: (RiskStatus | "")[] = ["", "open", "in_progress", "resolved", "dismissed"];

export function AtRiskScreen() {
  const t = useTranslations("careerServices");
  const locale = useLocale();
  const toast = useToast();
  const getErrorMessage = useApiErrorMessage();
  const qc = useQueryClient();

  const [statusFilter, setStatusFilter] = React.useState<RiskStatus | "">("");
  const [createOpen, setCreateOpen] = React.useState(false);
  const [studentId, setStudentId] = React.useState("");
  const [reason, setReason] = React.useState<RiskReason>("academic_performance");
  const [severity, setSeverity] = React.useState<RiskSeverity>("medium");
  const [notes, setNotes] = React.useState("");

  const [resolveTarget, setResolveTarget] = React.useState<AtRiskFlag | null>(null);
  const [resolveStatus, setResolveStatus] = React.useState<"resolved" | "dismissed">("resolved");
  const [resolutionNotes, setResolutionNotes] = React.useState("");

  const [openFlag, setOpenFlag] = React.useState<AtRiskFlag | null>(null);

  const query = useQuery({
    queryKey: ["career-services", "at-risk-flags", locale, statusFilter],
    queryFn: () => careerServicesApi.listAtRiskFlags(locale, { status: statusFilter }),
    retry: false,
  });

  const refresh = () =>
    qc.invalidateQueries({ queryKey: ["career-services", "at-risk-flags"] });

  const create = useMutation({
    mutationFn: () =>
      careerServicesApi.createAtRiskFlag(
        { student_id: studentId.trim(), reason, severity, notes: notes.trim() || null },
        locale,
      ),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("atRisk.createdToast") });
      setCreateOpen(false);
      setStudentId("");
      setNotes("");
      refresh();
    },
    onError: (error) => toast.show({ tone: "error", title: getErrorMessage(error) }),
  });

  const resolve = useMutation({
    mutationFn: () =>
      careerServicesApi.updateAtRiskFlagStatus(
        resolveTarget!.id,
        { status: resolveStatus, resolution_notes: resolutionNotes.trim() },
        locale,
      ),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("atRisk.resolvedToast") });
      setResolveTarget(null);
      setResolutionNotes("");
      setOpenFlag(null);
      refresh();
    },
    onError: (error) => toast.show({ tone: "error", title: getErrorMessage(error) }),
  });

  const markInProgress = useMutation({
    mutationFn: (flag: AtRiskFlag) =>
      careerServicesApi.updateAtRiskFlagStatus(flag.id, { status: "in_progress" }, locale),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("atRisk.updatedToast") });
      refresh();
    },
    onError: (error) => toast.show({ tone: "error", title: getErrorMessage(error) }),
  });

  const flags = query.data ?? [];
  const permissionState =
    query.isError && query.error instanceof ApiError ? (
      <CareerServicesPermissionGate error={query.error} bodyOverride={t("atRisk.permissionBody")} />
    ) : null;

  const createButton = (
    <Button onClick={() => setCreateOpen(true)} size="sm">
      <Plus className="size-4" strokeWidth={2} />
      {t("atRisk.flagStudent")}
    </Button>
  );

  const columns: ColumnDef<AtRiskFlag, unknown>[] = [
    {
      accessorKey: "student_id",
      header: t("atRisk.colStudent"),
      cell: ({ row }) => <span className="font-mono text-xs text-foreground">{row.original.student_id}</span>,
    },
    {
      accessorKey: "reason_label",
      header: t("atRisk.colReason"),
      cell: ({ row }) => <span className="text-foreground">{row.original.reason_label}</span>,
    },
    {
      accessorKey: "severity",
      header: t("atRisk.colSeverity"),
      cell: ({ row }) => (
        <StatusChip tone={SEVERITY_TONE[row.original.severity]} dot>
          {row.original.severity_label}
        </StatusChip>
      ),
    },
    {
      accessorKey: "status",
      header: t("atRisk.colStatus"),
      cell: ({ row }) => (
        <StatusChip tone={STATUS_TONE[row.original.status]}>{row.original.status_label}</StatusChip>
      ),
    },
    {
      id: "created",
      header: t("atRisk.colFlagged"),
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
        const resolved = r.status === "resolved" || r.status === "dismissed";
        return (
          <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
            {!resolved && r.status === "open" && (
              <Button variant="ghost" size="sm" onClick={() => markInProgress.mutate(r)}>
                {t("atRisk.startWork")}
              </Button>
            )}
            {!resolved && (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setResolveTarget(r);
                    setResolveStatus("resolved");
                  }}
                >
                  <CheckCircle2 className="size-4 text-[var(--content-success)]" strokeWidth={1.9} />
                  {t("atRisk.resolve")}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setResolveTarget(r);
                    setResolveStatus("dismissed");
                  }}
                >
                  <XCircle className="size-4 text-muted-foreground" strokeWidth={1.9} />
                  {t("atRisk.dismiss")}
                </Button>
              </>
            )}
            <Button variant="ghost" size="sm" onClick={() => setOpenFlag(r)}>
              {t("atRisk.viewDetail")}
            </Button>
          </div>
        );
      },
    },
  ];

  return (
    <CareerServicesShell
      title={t("atRisk.title")}
      description={t("atRisk.subtitle")}
      actions={!permissionState ? createButton : undefined}
    >
      {permissionState ?? (
        <div className="space-y-4">
          <FilterBar>
            <div className="flex flex-wrap gap-1.5" role="group" aria-label={t("atRisk.filterStatus")}>
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
                    {s === "" ? t("atRisk.allStatuses") : t(`riskStatus.${s}`)}
                  </button>
                );
              })}
            </div>
          </FilterBar>

          <DataTable
            columns={columns}
            data={flags}
            getRowId={(r) => r.id}
            loading={query.isPending}
            onRowClick={(r) => setOpenFlag(r)}
            activeRowId={openFlag?.id ?? undefined}
            empty={
              <EmptyState
                kind="empty"
                icon={AlertTriangle}
                title={t("atRisk.emptyTitle")}
                description={t("atRisk.emptyBody")}
              />
            }
          />
        </div>
      )}

      {/* Create flag */}
      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title={t("atRisk.createTitle")}
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
            label={t("atRisk.studentIdLabel")}
            required
            help={t("cohorts.studentIdHelp")}
            value={studentId}
            onChange={(e) => setStudentId(e.target.value)}
          />
          <Select
            label={t("atRisk.reasonLabel")}
            required
            value={reason}
            onChange={(e) => setReason(e.target.value as RiskReason)}
            options={RISK_REASONS.map((r) => ({ value: r, label: t(`riskReason.${r}`) }))}
          />
          <Select
            label={t("atRisk.severityLabel")}
            required
            value={severity}
            onChange={(e) => setSeverity(e.target.value as RiskSeverity)}
            options={RISK_SEVERITIES.map((s) => ({ value: s, label: t(`riskSeverity.${s}`) }))}
          />
          <Textarea
            label={t("atRisk.notesLabel")}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
          />
        </div>
      </Modal>

      {/* Resolve / dismiss */}
      <Modal
        open={!!resolveTarget}
        onClose={() => setResolveTarget(null)}
        title={resolveStatus === "resolved" ? t("atRisk.resolveTitle") : t("atRisk.dismissTitle")}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setResolveTarget(null)} disabled={resolve.isPending}>
              {t("cancel")}
            </Button>
            <Button loading={resolve.isPending} disabled={!resolutionNotes.trim()} onClick={() => resolve.mutate()}>
              {t("save")}
            </Button>
          </>
        }
      >
        <Textarea
          label={t("atRisk.resolutionNotesLabel")}
          required
          help={t("atRisk.resolutionNotesHelp")}
          value={resolutionNotes}
          onChange={(e) => setResolutionNotes(e.target.value)}
          rows={4}
        />
      </Modal>

      <AtRiskDetailSheet flag={openFlag} onClose={() => setOpenFlag(null)} />
    </CareerServicesShell>
  );
}

/* -------------------------------------------------------------------------- */
/* Student / flag detail sheet                                                 */
/* -------------------------------------------------------------------------- */

function AtRiskDetailSheet({ flag, onClose }: { flag: AtRiskFlag | null; onClose: () => void }) {
  const t = useTranslations("careerServices");
  const tc = useTranslations("common");
  const locale = useLocale();
  const open = flag != null;

  const interventionsQ = useQuery({
    queryKey: ["career-services", "interventions", "for-student", flag?.student_id],
    queryFn: () => careerServicesApi.listInterventions(locale, flag!.student_id),
    enabled: open,
    retry: false,
  });

  const interventions = interventionsQ.data ?? [];

  return (
    <DetailSheet
      open={open}
      onClose={onClose}
      title={t("atRisk.detailTitle")}
      subtitle={flag ? flag.student_id : undefined}
      status={
        flag ? (
          <>
            <StatusChip tone={STATUS_TONE[flag.status]}>{flag.status_label}</StatusChip>
            <StatusChip tone={SEVERITY_TONE[flag.severity]} dot>
              {flag.severity_label}
            </StatusChip>
          </>
        ) : undefined
      }
      width="md"
      closeLabel={tc("close")}
    >
      {flag && (
        <>
          <DetailSheetSection title={t("atRisk.detailFlagLabel")}>
            <dl>
              <DetailRow label={t("atRisk.colReason")}>{flag.reason_label}</DetailRow>
              <DetailRow label={t("atRisk.colSeverity")}>{flag.severity_label}</DetailRow>
              <DetailRow label={t("atRisk.colStatus")}>{flag.status_label}</DetailRow>
              <DetailRow label={t("atRisk.colFlagged")}>{formatDateTime(flag.created_at, locale)}</DetailRow>
            </dl>
            {flag.notes && (
              <div className="mt-3">
                <p className="type-caption font-semibold uppercase tracking-wide text-muted-foreground">
                  {t("atRisk.notesLabel")}
                </p>
                <p className="mt-1 whitespace-pre-wrap text-[0.8125rem] text-foreground">{flag.notes}</p>
              </div>
            )}
            {flag.resolution_notes && (
              <div className="mt-3">
                <p className="type-caption font-semibold uppercase tracking-wide text-muted-foreground">
                  {t("atRisk.detailResolutionLabel")}
                </p>
                <p className="mt-1 whitespace-pre-wrap text-[0.8125rem] text-foreground">
                  {flag.resolution_notes}
                </p>
              </div>
            )}
          </DetailSheetSection>

          <DetailSheetSection title={t("atRisk.detailInterventionsTitle")}>
            {interventionsQ.isPending ? (
              <div className="h-16 animate-skeleton rounded-lg bg-[var(--bg-muted)]" />
            ) : interventions.length === 0 ? (
              <p className="type-small text-muted-foreground">{t("atRisk.detailNoInterventions")}</p>
            ) : (
              <ul className="space-y-2.5">
                {interventions.slice(0, 8).map((iv) => (
                  <li key={iv.id} className="rounded-lg border border-border bg-[var(--bg-subtle)] p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[0.8125rem] font-semibold text-foreground">
                        {iv.intervention_type_label}
                      </span>
                      <StatusChip tone="neutral" size="sm">
                        {iv.outcome_label}
                      </StatusChip>
                    </div>
                    <p className="mt-1 line-clamp-3 type-small text-muted-foreground">{iv.description}</p>
                    <p className="mt-1 type-caption tabular-nums text-muted-foreground">
                      {formatDateTime(iv.created_at, locale)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </DetailSheetSection>
        </>
      )}
    </DetailSheet>
  );
}
