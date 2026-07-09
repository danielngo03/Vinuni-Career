"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { HeartPulse, Plus } from "lucide-react";
import { Button, Input, Modal, Select, Textarea, useToast } from "@/components/ui";
import {
  DataTable,
  EmptyState,
  FilterBar,
  StatusChip,
  type ChipTone,
  type ColumnDef,
} from "@/components/kit";
import { CareerServicesShell } from "./career-services-shell";
import { CareerServicesPermissionGate } from "./permission-gate";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import {
  ApiError,
  INTERVENTION_OUTCOMES,
  INTERVENTION_TYPES,
  careerServicesApi,
  type InterventionOutcome,
  type InterventionRecord,
  type InterventionType,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

const OUTCOME_TONE: Record<InterventionOutcome, ChipTone> = {
  no_outcome_yet: "warning",
  improved: "success",
  no_change: "neutral",
  escalated: "danger",
  resolved: "success",
};

export function InterventionsScreen() {
  const t = useTranslations("careerServices");
  const locale = useLocale();
  const toast = useToast();
  const getErrorMessage = useApiErrorMessage();
  const qc = useQueryClient();

  const [studentFilter, setStudentFilter] = React.useState("");
  const [createOpen, setCreateOpen] = React.useState(false);
  const [studentId, setStudentId] = React.useState("");
  const [type, setType] = React.useState<InterventionType>("advising_session");
  const [description, setDescription] = React.useState("");
  const [linkedAppointmentId, setLinkedAppointmentId] = React.useState("");
  const [linkedFlagId, setLinkedFlagId] = React.useState("");

  const [outcomeTarget, setOutcomeTarget] = React.useState<InterventionRecord | null>(null);
  const [outcome, setOutcome] = React.useState<InterventionOutcome>("improved");

  const query = useQuery({
    queryKey: ["career-services", "interventions", locale, studentFilter],
    queryFn: () => careerServicesApi.listInterventions(locale, studentFilter || undefined),
    retry: false,
  });

  const refresh = () =>
    qc.invalidateQueries({ queryKey: ["career-services", "interventions"] });

  const closeCreate = () => {
    setCreateOpen(false);
    setStudentId("");
    setDescription("");
    setLinkedAppointmentId("");
    setLinkedFlagId("");
  };

  const create = useMutation({
    mutationFn: () =>
      careerServicesApi.createIntervention(
        {
          student_id: studentId.trim(),
          intervention_type: type,
          description: description.trim(),
          linked_appointment_id: linkedAppointmentId.trim() || null,
          linked_at_risk_flag_id: linkedFlagId.trim() || null,
        },
        locale,
      ),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("interventions.createdToast") });
      closeCreate();
      refresh();
    },
    onError: (error) => toast.show({ tone: "error", title: getErrorMessage(error) }),
  });

  const updateOutcome = useMutation({
    mutationFn: () =>
      careerServicesApi.updateInterventionOutcome(outcomeTarget!.id, outcome, locale),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("interventions.updatedToast") });
      setOutcomeTarget(null);
      refresh();
    },
    onError: (error) => toast.show({ tone: "error", title: getErrorMessage(error) }),
  });

  const records = query.data ?? [];
  const permissionState =
    query.isError && query.error instanceof ApiError ? (
      <CareerServicesPermissionGate error={query.error} bodyOverride={t("interventions.permissionBody")} />
    ) : null;

  const logButton = (
    <Button onClick={() => setCreateOpen(true)} size="sm">
      <Plus className="size-4" strokeWidth={2} />
      {t("interventions.logIntervention")}
    </Button>
  );

  const columns: ColumnDef<InterventionRecord, unknown>[] = [
    {
      accessorKey: "student_id",
      header: t("interventions.colStudent"),
      cell: ({ row }) => <span className="font-mono text-xs text-foreground">{row.original.student_id}</span>,
    },
    {
      accessorKey: "intervention_type_label",
      header: t("interventions.colType"),
      cell: ({ row }) => <span className="text-foreground">{row.original.intervention_type_label}</span>,
    },
    {
      id: "description",
      header: t("interventions.colDescription"),
      enableSorting: false,
      cell: ({ row }) => (
        <span className="line-clamp-2 block max-w-[280px] type-small text-muted-foreground">
          {row.original.description}
        </span>
      ),
    },
    {
      accessorKey: "outcome",
      header: t("interventions.colOutcome"),
      cell: ({ row }) => (
        <StatusChip tone={OUTCOME_TONE[row.original.outcome]}>{row.original.outcome_label}</StatusChip>
      ),
    },
    {
      id: "linked",
      header: t("interventions.colLinked"),
      enableSorting: false,
      cell: ({ row }) =>
        row.original.linked_appointment_id || row.original.linked_at_risk_flag_id ? (
          <div className="flex flex-col gap-0.5 type-caption text-muted-foreground">
            {row.original.linked_appointment_id && <span>{t("interventions.linkedAppointment")}</span>}
            {row.original.linked_at_risk_flag_id && <span>{t("interventions.linkedAtRisk")}</span>}
          </div>
        ) : (
          <span className="type-caption text-muted-foreground">—</span>
        ),
    },
    {
      id: "created",
      header: t("interventions.colCreated"),
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
      cell: ({ row }) => (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setOutcomeTarget(row.original);
            setOutcome(row.original.outcome === "no_outcome_yet" ? "improved" : row.original.outcome);
          }}
        >
          {t("interventions.recordOutcome")}
        </Button>
      ),
    },
  ];

  return (
    <CareerServicesShell
      title={t("interventions.title")}
      description={t("interventions.subtitle")}
      actions={!permissionState ? logButton : undefined}
    >
      {permissionState ?? (
        <div className="space-y-4">
          <FilterBar
            search={{
              value: studentFilter,
              onChange: setStudentFilter,
              placeholder: t("interventions.filterStudentPlaceholder"),
              ariaLabel: t("interventions.filterStudent"),
            }}
          />

          <DataTable
            columns={columns}
            data={records}
            getRowId={(r) => r.id}
            loading={query.isPending}
            empty={
              <EmptyState
                kind="empty"
                icon={HeartPulse}
                title={t("interventions.emptyTitle")}
                description={t("interventions.emptyBody")}
              />
            }
          />
        </div>
      )}

      {/* Log intervention */}
      <Modal
        open={createOpen}
        onClose={closeCreate}
        title={t("interventions.createTitle")}
        size="md"
        footer={
          <>
            <Button variant="ghost" onClick={closeCreate} disabled={create.isPending}>
              {t("cancel")}
            </Button>
            <Button
              loading={create.isPending}
              disabled={!studentId.trim() || !description.trim()}
              onClick={() => create.mutate()}
            >
              {t("save")}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label={t("interventions.studentIdLabel")}
            required
            help={t("cohorts.studentIdHelp")}
            value={studentId}
            onChange={(e) => setStudentId(e.target.value)}
          />
          <Select
            label={t("interventions.typeLabel")}
            required
            value={type}
            onChange={(e) => setType(e.target.value as InterventionType)}
            options={INTERVENTION_TYPES.map((it) => ({ value: it, label: t(`interventionType.${it}`) }))}
          />
          <Textarea
            label={t("interventions.descriptionLabel")}
            required
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label={t("interventions.linkedAppointmentLabel")}
              help={t("interventions.linkedIdHelp")}
              value={linkedAppointmentId}
              onChange={(e) => setLinkedAppointmentId(e.target.value)}
            />
            <Input
              label={t("interventions.linkedAtRiskLabel")}
              help={t("interventions.linkedIdHelp")}
              value={linkedFlagId}
              onChange={(e) => setLinkedFlagId(e.target.value)}
            />
          </div>
        </div>
      </Modal>

      {/* Record outcome */}
      <Modal
        open={!!outcomeTarget}
        onClose={() => setOutcomeTarget(null)}
        title={t("interventions.recordOutcome")}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setOutcomeTarget(null)} disabled={updateOutcome.isPending}>
              {t("cancel")}
            </Button>
            <Button loading={updateOutcome.isPending} onClick={() => updateOutcome.mutate()}>
              {t("save")}
            </Button>
          </>
        }
      >
        <Select
          label={t("interventions.outcomeLabel")}
          value={outcome}
          onChange={(e) => setOutcome(e.target.value as InterventionOutcome)}
          options={INTERVENTION_OUTCOMES.map((o) => ({ value: o, label: t(`interventionOutcome.${o}`) }))}
        />
      </Modal>
    </CareerServicesShell>
  );
}
