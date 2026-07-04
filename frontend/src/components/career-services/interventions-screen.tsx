"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FirstAidKit, PlusCircle } from "@phosphor-icons/react";
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
  INTERVENTION_OUTCOMES,
  INTERVENTION_TYPES,
  careerServicesApi,
  type InterventionOutcome,
  type InterventionRecord,
  type InterventionType,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

const OUTCOME_TONE: Record<InterventionOutcome, "pending" | "accepted" | "closed" | "rejected"> = {
  no_outcome_yet: "pending",
  improved: "accepted",
  no_change: "closed",
  escalated: "rejected",
  resolved: "accepted",
};

export function InterventionsScreen() {
  const t = useTranslations("careerServices");
  const locale = useLocale();
  const toast = useToast();
  const getErrorMessage = useApiErrorMessage();
  const qc = useQueryClient();

  const [studentFilter, setStudentFilter] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [studentId, setStudentId] = useState("");
  const [type, setType] = useState<InterventionType>("advising_session");
  const [description, setDescription] = useState("");
  const [linkedAppointmentId, setLinkedAppointmentId] = useState("");
  const [linkedFlagId, setLinkedFlagId] = useState("");

  const [outcomeTarget, setOutcomeTarget] = useState<InterventionRecord | null>(null);
  const [outcome, setOutcome] = useState<InterventionOutcome>("improved");

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

  const records = useMemo(() => query.data ?? [], [query.data]);
  const permissionState =
    query.isError && query.error instanceof ApiError ? (
      <CareerServicesPermissionGate error={query.error} bodyOverride={t("interventions.permissionBody")} />
    ) : null;

  const columns: Column<InterventionRecord>[] = [
    {
      key: "student",
      header: t("interventions.colStudent"),
      cell: (r) => <span className="font-mono text-xs">{r.student_id}</span>,
    },
    {
      key: "type",
      header: t("interventions.colType"),
      cell: (r) => <span>{r.intervention_type_label}</span>,
    },
    {
      key: "description",
      header: t("interventions.colDescription"),
      cell: (r) => <span className="line-clamp-2 max-w-[280px] text-sm">{r.description}</span>,
    },
    {
      key: "outcome",
      header: t("interventions.colOutcome"),
      cell: (r) => <StatusBadge tone={OUTCOME_TONE[r.outcome]}>{r.outcome_label}</StatusBadge>,
    },
    {
      key: "linked",
      header: t("interventions.colLinked"),
      cell: (r) =>
        r.linked_appointment_id || r.linked_at_risk_flag_id ? (
          <div className="flex flex-col gap-0.5 text-xs text-[var(--text-muted)]">
            {r.linked_appointment_id && <span>{t("interventions.linkedAppointment")}</span>}
            {r.linked_at_risk_flag_id && <span>{t("interventions.linkedAtRisk")}</span>}
          </div>
        ) : (
          <span className="text-xs text-[var(--text-muted)]">—</span>
        ),
    },
    {
      key: "created",
      header: t("interventions.colCreated"),
      cell: (r) => <span className="text-xs text-[var(--text-secondary)]">{formatDateTime(r.created_at, locale)}</span>,
    },
    {
      key: "actions",
      header: t("interventions.colActions"),
      cell: (r) => (
        <Button
          variant="ghost"
          size="xs"
          onClick={() => {
            setOutcomeTarget(r);
            setOutcome(r.outcome === "no_outcome_yet" ? "improved" : r.outcome);
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
      actions={
        !permissionState && (
          <div className="flex items-center gap-2">
            <Input
              aria-label={t("interventions.filterStudent")}
              placeholder={t("interventions.filterStudentPlaceholder")}
              value={studentFilter}
              onChange={(e) => setStudentFilter(e.target.value)}
              className="max-w-[220px]"
            />
            <Button onClick={() => setCreateOpen(true)}>
              <PlusCircle aria-hidden weight="bold" className="size-4" />
              {t("interventions.logIntervention")}
            </Button>
          </div>
        )
      }
    >
      {permissionState ?? (
        <DataTable
          columns={columns}
          rows={records}
          getRowId={(r) => r.id}
          loading={query.isLoading}
          caption={t("interventions.title")}
          empty={{
            kind: "empty",
            icon: FirstAidKit,
            title: t("interventions.emptyTitle"),
            description: t("interventions.emptyBody"),
          }}
        />
      )}

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
