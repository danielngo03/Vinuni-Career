"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle, Flag, PlusCircle, XCircle } from "@phosphor-icons/react";
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
  RISK_REASONS,
  RISK_SEVERITIES,
  careerServicesApi,
  type AtRiskFlag,
  type RiskReason,
  type RiskSeverity,
  type RiskStatus,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

const SEVERITY_TONE: Record<RiskSeverity, "closed" | "pending" | "rejected"> = {
  low: "closed",
  medium: "pending",
  high: "rejected",
};

const STATUS_TONE: Record<RiskStatus, "pending" | "active" | "accepted" | "closed"> = {
  open: "pending",
  in_progress: "active",
  resolved: "accepted",
  dismissed: "closed",
};

export function AtRiskScreen() {
  const t = useTranslations("careerServices");
  const locale = useLocale();
  const toast = useToast();
  const getErrorMessage = useApiErrorMessage();
  const qc = useQueryClient();

  const [statusFilter, setStatusFilter] = useState<RiskStatus | "">("");
  const [createOpen, setCreateOpen] = useState(false);
  const [studentId, setStudentId] = useState("");
  const [reason, setReason] = useState<RiskReason>("academic_performance");
  const [severity, setSeverity] = useState<RiskSeverity>("medium");
  const [notes, setNotes] = useState("");

  const [resolveTarget, setResolveTarget] = useState<AtRiskFlag | null>(null);
  const [resolveStatus, setResolveStatus] = useState<"resolved" | "dismissed">("resolved");
  const [resolutionNotes, setResolutionNotes] = useState("");

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

  const flags = useMemo(() => query.data ?? [], [query.data]);
  const permissionState =
    query.isError && query.error instanceof ApiError ? (
      <CareerServicesPermissionGate error={query.error} bodyOverride={t("atRisk.permissionBody")} />
    ) : null;

  const columns: Column<AtRiskFlag>[] = [
    {
      key: "student",
      header: t("atRisk.colStudent"),
      cell: (r) => <span className="font-mono text-xs">{r.student_id}</span>,
    },
    {
      key: "reason",
      header: t("atRisk.colReason"),
      cell: (r) => <span>{r.reason_label}</span>,
    },
    {
      key: "severity",
      header: t("atRisk.colSeverity"),
      cell: (r) => <StatusBadge tone={SEVERITY_TONE[r.severity]}>{r.severity_label}</StatusBadge>,
    },
    {
      key: "status",
      header: t("atRisk.colStatus"),
      cell: (r) => <StatusBadge tone={STATUS_TONE[r.status]}>{r.status_label}</StatusBadge>,
    },
    {
      key: "created",
      header: t("atRisk.colFlagged"),
      cell: (r) => <span className="text-xs text-[var(--text-secondary)]">{formatDateTime(r.created_at, locale)}</span>,
    },
    {
      key: "actions",
      header: t("atRisk.colActions"),
      cell: (r) =>
        r.status === "resolved" || r.status === "dismissed" ? (
          <span className="text-xs text-[var(--text-muted)]">{r.resolution_notes}</span>
        ) : (
          <div className="flex gap-1.5">
            {r.status === "open" && (
              <Button variant="ghost" size="xs" onClick={() => markInProgress.mutate(r)}>
                {t("atRisk.startWork")}
              </Button>
            )}
            <Button
              variant="ghost"
              size="xs"
              onClick={() => {
                setResolveTarget(r);
                setResolveStatus("resolved");
              }}
            >
              <CheckCircle aria-hidden weight="bold" className="size-4 text-[var(--color-success)]" />
              {t("atRisk.resolve")}
            </Button>
            <Button
              variant="ghost"
              size="xs"
              onClick={() => {
                setResolveTarget(r);
                setResolveStatus("dismissed");
              }}
            >
              <XCircle aria-hidden weight="bold" className="size-4 text-[var(--text-muted)]" />
              {t("atRisk.dismiss")}
            </Button>
          </div>
        ),
    },
  ];

  return (
    <CareerServicesShell
      title={t("atRisk.title")}
      description={t("atRisk.subtitle")}
      actions={
        !permissionState && (
          <div className="flex items-center gap-2">
            <Select
              aria-label={t("atRisk.filterStatus")}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as RiskStatus | "")}
              options={[
                { value: "", label: t("atRisk.allStatuses") },
                { value: "open", label: t("riskStatus.open") },
                { value: "in_progress", label: t("riskStatus.in_progress") },
                { value: "resolved", label: t("riskStatus.resolved") },
                { value: "dismissed", label: t("riskStatus.dismissed") },
              ]}
            />
            <Button onClick={() => setCreateOpen(true)}>
              <PlusCircle aria-hidden weight="bold" className="size-4" />
              {t("atRisk.flagStudent")}
            </Button>
          </div>
        )
      }
    >
      {permissionState ?? (
        <DataTable
          columns={columns}
          rows={flags}
          getRowId={(r) => r.id}
          loading={query.isLoading}
          caption={t("atRisk.title")}
          empty={{
            kind: "empty",
            icon: Flag,
            title: t("atRisk.emptyTitle"),
            description: t("atRisk.emptyBody"),
          }}
        />
      )}

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
            <Button
              loading={create.isPending}
              disabled={!studentId.trim()}
              onClick={() => create.mutate()}
            >
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
            <Button
              loading={resolve.isPending}
              disabled={!resolutionNotes.trim()}
              onClick={() => resolve.mutate()}
            >
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
    </CareerServicesShell>
  );
}
