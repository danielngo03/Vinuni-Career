"use client";

import { useState, useEffect, useRef, useId } from "react";
import { useTranslations, useLocale } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useQuery } from "@tanstack/react-query";
import {
  Siren,
  Plus,
  Trash2,
  CheckCheck,
  CircleCheck,
} from "lucide-react";
import { Warning, WarningCircle, PencilSimple } from "@phosphor-icons/react";
import { PageHeader } from "@/components/layout/page-header";
import {
  Tabs,
  TabPanel,
  StatusBadge,
  Skeleton,
  EmptyState,
  DataTable,
  Input,
  Select,
  Sheet,
  Modal,
  Switch,
  Button,
  SegmentedControl,
  useToast,
  type Column,
  type StatusTone,
} from "@/components/ui";
import {
  alertsApi,
  type AlertRule,
  type AlertIncident,
  type AlertMetric,
  type AlertComparison,
  type AlertSeverity,
  type IncidentStatus,
  type AlertRuleCreateBody,
  type AlertRuleUpdateBody,
} from "@/lib/api/alerts";
import { formatDateTime } from "@/lib/format";

/* -------------------------------------------------------------------------- */
/* Helpers                                                                     */
/* -------------------------------------------------------------------------- */

function severityTone(s: AlertSeverity): StatusTone {
  if (s === "critical") return "rejected";
  if (s === "warning") return "pending";
  return "info";
}

function statusTone(s: IncidentStatus): StatusTone {
  if (s === "open") return "rejected";
  if (s === "acknowledged") return "pending";
  return "accepted";
}

/* -------------------------------------------------------------------------- */
/* Detail row (Sheet)                                                          */
/* -------------------------------------------------------------------------- */

function DetailRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-[var(--border-subtle)] py-2.5 last:border-0">
      <span className="text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {label}
      </span>
      <span className="break-all text-sm text-[var(--text-primary)]">
        {children}
      </span>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Confirm dialog                                                              */
/* -------------------------------------------------------------------------- */

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  body: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  dangerous?: boolean;
  loading?: boolean;
}

function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onCancel,
  dangerous,
  loading,
}: ConfirmDialogProps) {
  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={title}
      size="sm"
      closeLabel={cancelLabel}
      footer={
        <>
          <Button variant="ghost" onClick={onCancel} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button
            variant={dangerous ? "danger" : "primary"}
            onClick={onConfirm}
            loading={loading}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <p className="text-sm text-[var(--text-secondary)]">{body}</p>
    </Modal>
  );
}

/* ========================================================================== */
/* INCIDENTS TAB                                                               */
/* ========================================================================== */

type IncidentFilter = IncidentStatus | "all";

function IncidentsTab() {
  const t = useTranslations("adminConsole.alerts");
  const locale = useLocale();
  const toast = useToast();
  const qc = useQueryClient();

  const [statusFilter, setStatusFilter] = useState<IncidentFilter>("open");
  const [cursor, setCursor] = useState<string | null>(null);
  const [items, setItems] = useState<AlertIncident[]>([]);
  const seenIds = useRef<Set<string>>(new Set());

  // Reset list when filter changes
  useEffect(() => {
    setCursor(null);
    setItems([]);
    seenIds.current = new Set();
  }, [statusFilter]);

  const pageQuery = useQuery({
    queryKey: ["alerts", "incidents", statusFilter, cursor] as const,
    queryFn: () =>
      alertsApi.listIncidents({
        status: statusFilter,
        cursor: cursor ?? undefined,
        limit: 25,
      }),
    staleTime: 30_000,
    refetchInterval: (() => {
      if (typeof document !== "undefined" && document.hidden) return false;
      return 30_000;
    })(),
    retry: 1,
  });

  // Accumulate pages (dedupe by id)
  useEffect(() => {
    if (!pageQuery.data) return;
    if (cursor === null) {
      // First page — replace entirely
      setItems(pageQuery.data.items);
      seenIds.current = new Set(pageQuery.data.items.map((it) => it.id));
    } else {
      const newItems = pageQuery.data.items.filter(
        (it) => !seenIds.current.has(it.id),
      );
      newItems.forEach((it) => seenIds.current.add(it.id));
      setItems((prev) => [...prev, ...newItems]);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageQuery.data]);

  const hasMore =
    pageQuery.data?.next_cursor != null && !pageQuery.isFetching;

  // Open incident summary count
  const openCount = statusFilter === "open" ? items.length : null;

  // Detail sheet
  const [detailIncident, setDetailIncident] = useState<AlertIncident | null>(
    null,
  );

  // Confirm dialogs
  const [confirmAck, setConfirmAck] = useState<AlertIncident | null>(null);
  const [confirmResolve, setConfirmResolve] = useState<AlertIncident | null>(
    null,
  );

  function invalidateAndReset() {
    void qc.invalidateQueries({ queryKey: ["alerts", "incidents"] });
    setCursor(null);
    setItems([]);
    seenIds.current = new Set();
  }

  const ackMutation = useMutation({
    mutationFn: (id: string) => alertsApi.acknowledgeIncident(id),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("incidents.acknowledgeSuccess") });
      setConfirmAck(null);
      invalidateAndReset();
    },
    onError: () => {
      toast.show({ tone: "error", title: t("incidents.acknowledgeError") });
    },
  });

  const resolveMutation = useMutation({
    mutationFn: (id: string) => alertsApi.resolveIncident(id),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("incidents.resolveSuccess") });
      setConfirmResolve(null);
      invalidateAndReset();
    },
    onError: () => {
      toast.show({ tone: "error", title: t("incidents.resolveError") });
    },
  });

  const filterOptions = [
    { value: "open", label: t("incidentStatus.open") },
    { value: "acknowledged", label: t("incidentStatus.acknowledged") },
    { value: "resolved", label: t("incidentStatus.resolved") },
    { value: "all", label: t("incidentStatus.all") },
  ];

  const columns: Column<AlertIncident>[] = [
    {
      key: "severity",
      header: t("incidents.col.severity"),
      cell: (row) => (
        <button
          type="button"
          className="text-left focus:outline-none"
          onClick={() => setDetailIncident(row)}
          aria-label={`${t("incidents.sheet.title")} — ${row.id}`}
        >
          <StatusBadge tone={severityTone(row.severity)}>
            {t(`severity.${row.severity}`)}
          </StatusBadge>
        </button>
      ),
    },
    {
      key: "metric",
      header: t("incidents.col.metric"),
      cell: (row) => (
        <span className="text-xs text-[var(--text-secondary)]">
          {t(`metric.${row.metric}`)}
        </span>
      ),
    },
    {
      key: "message",
      header: t("incidents.col.message"),
      cell: (row) => (
        <button
          type="button"
          className="text-left text-sm text-[var(--text-primary)] line-clamp-2 max-w-xs focus:outline-none hover:underline underline-offset-2"
          onClick={() => setDetailIncident(row)}
        >
          {row.message}
        </button>
      ),
    },
    {
      key: "triggered_at",
      header: t("incidents.col.triggered"),
      cell: (row) => (
        <span className="text-xs tabular-nums text-[var(--text-muted)] whitespace-nowrap">
          {formatDateTime(row.triggered_at, locale)}
        </span>
      ),
    },
    {
      key: "status",
      header: t("incidents.col.status"),
      cell: (row) => (
        <StatusBadge tone={statusTone(row.status)}>
          {t(`incidentStatus.${row.status}`)}
        </StatusBadge>
      ),
    },
    {
      key: "actions",
      header: t("incidents.col.actions"),
      align: "right",
      cell: (row) => (
        <div className="flex items-center justify-end gap-2">
          {row.status === "open" && (
            <button
              type="button"
              onClick={() => setConfirmAck(row)}
              className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/50"
              aria-label={`${t("incidents.acknowledge")} — ${row.id}`}
            >
              <CheckCheck aria-hidden className="size-3.5" />
              {t("incidents.acknowledge")}
            </button>
          )}
          {(row.status === "open" || row.status === "acknowledged") && (
            <button
              type="button"
              onClick={() => setConfirmResolve(row)}
              className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/50"
              aria-label={`${t("incidents.resolve")} — ${row.id}`}
            >
              <CircleCheck aria-hidden className="size-3.5" />
              {t("incidents.resolve")}
            </button>
          )}
        </div>
      ),
    },
  ];

  const isInitialLoad = pageQuery.isPending && cursor === null && items.length === 0;

  return (
    <>
      {/* Open incident count tonal banner */}
      {openCount !== null && openCount > 0 && (
        <div className="mb-4 flex items-center gap-2 rounded-xl bg-[var(--red-50)] px-4 py-3 text-sm font-semibold text-[var(--brand-red)]">
          <Warning aria-hidden weight="fill" className="size-4 shrink-0" />
          {openCount === 1
            ? t("openSummary", { count: openCount })
            : t("openSummaryPlural", { count: openCount })}
        </div>
      )}
      {openCount === 0 && statusFilter === "open" && !isInitialLoad && (
        <div className="mb-4 flex items-center gap-2 rounded-xl bg-[var(--bg-subtle)] px-4 py-3 text-sm text-[var(--text-muted)]">
          {t("noOpenIncidents")}
        </div>
      )}

      {/* Status filter */}
      <div className="mb-4">
        <SegmentedControl
          ariaLabel={t("incidents.statusFilter")}
          value={statusFilter}
          onValueChange={(v) => setStatusFilter(v as IncidentFilter)}
          options={filterOptions}
          size="sm"
        />
      </div>

      {/* Table */}
      {isInitialLoad ? (
        <Skeleton className="h-64 w-full rounded-xl" />
      ) : pageQuery.isError && items.length === 0 ? (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("incidents.errorTitle")}
          description={t("incidents.errorBody")}
          action={
            <button
              onClick={() => void pageQuery.refetch()}
              className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
            >
              {t("retry")}
            </button>
          }
        />
      ) : (
        <DataTable
          columns={columns}
          rows={items}
          getRowId={(r) => r.id}
          caption={t("tabs.incidents")}
          empty={{
            kind: "empty",
            title: t("incidents.emptyTitle"),
            description: t("incidents.emptyBody"),
          }}
        />
      )}

      {hasMore && (
        <div className="mt-4 flex justify-center">
          <Button
            variant="ghost"
            onClick={() => setCursor(pageQuery.data!.next_cursor!)}
          >
            {t("incidents.loadMore")}
          </Button>
        </div>
      )}
      {pageQuery.isFetching && cursor !== null && (
        <div className="mt-4 flex justify-center">
          <Skeleton className="h-8 w-24 rounded-lg" />
        </div>
      )}

      {/* Detail sheet */}
      <Sheet
        open={detailIncident !== null}
        onClose={() => setDetailIncident(null)}
        title={t("incidents.sheet.title")}
        closeLabel={t("incidents.sheet.closeLabel")}
      >
        {detailIncident && (
          <div className="space-y-0">
            <DetailRow label={t("incidents.sheet.labelMetric")}>
              {t(`metric.${detailIncident.metric}`)}
            </DetailRow>
            <DetailRow label={t("incidents.sheet.labelMessage")}>
              {detailIncident.message}
            </DetailRow>
            <DetailRow label={t("incidents.sheet.labelValue")}>
              <span className="font-mono text-sm">
                {detailIncident.value}
              </span>
            </DetailRow>
            <DetailRow label={t("incidents.sheet.labelThreshold")}>
              <span className="font-mono text-sm">
                {detailIncident.threshold}
              </span>
            </DetailRow>
            <DetailRow label={t("incidents.sheet.labelRuleId")}>
              <span className="font-mono text-xs text-[var(--text-muted)]">
                {detailIncident.rule_id}
              </span>
            </DetailRow>
            <div className="pt-4">
              <span className="block text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)] mb-2">
                {t("incidents.sheet.timelineTitle")}
              </span>
              <div className="space-y-2 pl-2 border-l-2 border-[var(--border-subtle)]">
                <div className="flex flex-col gap-0.5 pl-3">
                  <span className="text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                    {t("incidents.sheet.labelTriggered")}
                  </span>
                  <span className="text-sm text-[var(--text-primary)]">
                    {formatDateTime(detailIncident.triggered_at, locale)}
                  </span>
                </div>
                <div className="flex flex-col gap-0.5 pl-3">
                  <span className="text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                    {t("incidents.sheet.labelAcknowledged")}
                  </span>
                  <span className="text-sm text-[var(--text-primary)]">
                    {detailIncident.acknowledged_at
                      ? formatDateTime(detailIncident.acknowledged_at, locale)
                      : t("incidents.sheet.notYet")}
                  </span>
                </div>
                {detailIncident.acknowledged_by && (
                  <div className="flex flex-col gap-0.5 pl-3">
                    <span className="text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                      {t("incidents.sheet.labelAcknowledgedBy")}
                    </span>
                    <span className="text-sm text-[var(--text-primary)]">
                      {detailIncident.acknowledged_by}
                    </span>
                  </div>
                )}
                <div className="flex flex-col gap-0.5 pl-3">
                  <span className="text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                    {t("incidents.sheet.labelResolved")}
                  </span>
                  <span className="text-sm text-[var(--text-primary)]">
                    {detailIncident.resolved_at
                      ? formatDateTime(detailIncident.resolved_at, locale)
                      : t("incidents.sheet.notYet")}
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}
      </Sheet>

      {/* Acknowledge confirm */}
      <ConfirmDialog
        open={confirmAck !== null}
        title={t("incidents.acknowledgeConfirmTitle")}
        body={t("incidents.acknowledgeConfirmBody")}
        confirmLabel={t("incidents.confirm")}
        cancelLabel={t("incidents.cancel")}
        onConfirm={() => {
          if (confirmAck) ackMutation.mutate(confirmAck.id);
        }}
        onCancel={() => setConfirmAck(null)}
        loading={ackMutation.isPending}
      />

      {/* Resolve confirm */}
      <ConfirmDialog
        open={confirmResolve !== null}
        title={t("incidents.resolveConfirmTitle")}
        body={t("incidents.resolveConfirmBody")}
        confirmLabel={t("incidents.confirm")}
        cancelLabel={t("incidents.cancel")}
        onConfirm={() => {
          if (confirmResolve) resolveMutation.mutate(confirmResolve.id);
        }}
        onCancel={() => setConfirmResolve(null)}
        loading={resolveMutation.isPending}
      />
    </>
  );
}

/* ========================================================================== */
/* RULES TAB                                                                   */
/* ========================================================================== */

interface RuleFormState {
  name: string;
  metric: AlertMetric;
  comparison: AlertComparison;
  threshold: string;
  window_days: string;
  severity: AlertSeverity;
  enabled: boolean;
  channels: string[];
}

interface RuleFormErrors {
  name?: string;
  threshold?: string;
  window_days?: string;
}

const DEFAULT_FORM: RuleFormState = {
  name: "",
  metric: "ai_error_rate",
  comparison: "gt",
  threshold: "",
  window_days: "1",
  severity: "warning",
  enabled: true,
  channels: ["in_app"],
};

function ruleToForm(r: AlertRule): RuleFormState {
  return {
    name: r.name,
    metric: r.metric,
    comparison: r.comparison,
    threshold: String(r.threshold),
    window_days: String(r.window_days),
    severity: r.severity,
    enabled: r.enabled,
    channels: r.channels,
  };
}

const METRIC_OPTIONS: AlertMetric[] = [
  "ai_spend_vs_budget_pct",
  "ai_error_rate",
  "queue_depth",
  "outbox_failed",
];

const COMPARISON_OPTIONS: AlertComparison[] = ["gt", "gte", "lt", "lte"];

const SEVERITY_OPTIONS: AlertSeverity[] = ["info", "warning", "critical"];

const CHANNEL_OPTIONS = ["in_app", "email"];

function RuleFormSheet({
  open,
  editing,
  onClose,
}: {
  open: boolean;
  editing: AlertRule | null;
  onClose: () => void;
}) {
  const t = useTranslations("adminConsole.alerts");
  const toast = useToast();
  const qc = useQueryClient();

  const [form, setForm] = useState<RuleFormState>(
    editing ? ruleToForm(editing) : { ...DEFAULT_FORM },
  );
  const [errors, setErrors] = useState<RuleFormErrors>({});

  // Reset form when the sheet is opened with a new editing target
  useEffect(() => {
    if (open) {
      setForm(editing ? ruleToForm(editing) : { ...DEFAULT_FORM });
      setErrors({});
    }
  }, [open, editing]);

  function patch(partial: Partial<RuleFormState>) {
    setForm((f) => ({ ...f, ...partial }));
    setErrors((e) => {
      const next = { ...e };
      for (const k of Object.keys(partial) as (keyof RuleFormState)[]) {
        delete (next as Record<string, string | undefined>)[k];
      }
      return next;
    });
  }

  function validate(): RuleFormErrors {
    const errs: RuleFormErrors = {};
    if (!form.name.trim()) errs.name = t("rules.sheet.validationName");
    const thr = parseFloat(form.threshold);
    if (!isFinite(thr)) errs.threshold = t("rules.sheet.validationThreshold");
    const win = parseInt(form.window_days, 10);
    if (!Number.isInteger(win) || win < 1 || win > 90)
      errs.window_days = t("rules.sheet.validationWindow");
    return errs;
  }

  const createMutation = useMutation({
    mutationFn: (body: AlertRuleCreateBody) => alertsApi.createRule(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["alerts", "rules"] });
      toast.show({ tone: "success", title: t("rules.sheet.saveSuccess") });
      onClose();
    },
    onError: () => {
      toast.show({ tone: "error", title: t("rules.sheet.saveError") });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: AlertRuleUpdateBody }) =>
      alertsApi.updateRule(id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["alerts", "rules"] });
      toast.show({ tone: "success", title: t("rules.sheet.saveSuccess") });
      onClose();
    },
    onError: () => {
      toast.show({ tone: "error", title: t("rules.sheet.saveError") });
    },
  });

  const isPending = createMutation.isPending || updateMutation.isPending;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length > 0) {
      setErrors(errs);
      return;
    }

    const body: AlertRuleCreateBody = {
      name: form.name.trim(),
      metric: form.metric,
      comparison: form.comparison,
      threshold: parseFloat(form.threshold),
      window_days: parseInt(form.window_days, 10),
      severity: form.severity,
      enabled: form.enabled,
      channels: form.channels,
    };

    if (editing) {
      updateMutation.mutate({ id: editing.id, body });
    } else {
      createMutation.mutate(body);
    }
  }

  function toggleChannel(ch: string) {
    const next = form.channels.includes(ch)
      ? form.channels.filter((c) => c !== ch)
      : [...form.channels, ch];
    patch({ channels: next });
  }

  return (
    <Sheet
      open={open}
      onClose={() => {
        if (!isPending) onClose();
      }}
      title={editing ? t("rules.sheet.editTitle") : t("rules.sheet.addTitle")}
      closeLabel={t("rules.sheet.cancel")}
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <Input
          id="rule-name"
          label={t("rules.sheet.labelName")}
          value={form.name}
          onChange={(e) => patch({ name: e.target.value })}
          error={errors.name}
          required
        />

        <Select
          id="rule-metric"
          label={t("rules.sheet.labelMetric")}
          value={form.metric}
          onChange={(e) => patch({ metric: e.target.value as AlertMetric })}
          options={METRIC_OPTIONS.map((m) => ({
            value: m,
            label: t(`metric.${m}`),
          }))}
          required
        />

        <Select
          id="rule-comparison"
          label={t("rules.sheet.labelComparison")}
          value={form.comparison}
          onChange={(e) =>
            patch({ comparison: e.target.value as AlertComparison })
          }
          options={COMPARISON_OPTIONS.map((c) => ({
            value: c,
            label: t(`comparison.${c}`),
          }))}
          required
        />

        <Input
          id="rule-threshold"
          type="number"
          inputMode="decimal"
          step="any"
          label={t("rules.sheet.labelThreshold")}
          help={t("rules.sheet.labelThresholdHelp")}
          value={form.threshold}
          onChange={(e) => patch({ threshold: e.target.value })}
          error={errors.threshold}
          required
        />

        <Input
          id="rule-window"
          type="number"
          inputMode="numeric"
          min={1}
          max={90}
          step={1}
          label={t("rules.sheet.labelWindowDays")}
          help={t("rules.sheet.labelWindowDaysHelp")}
          value={form.window_days}
          onChange={(e) => patch({ window_days: e.target.value })}
          error={errors.window_days}
          required
        />

        <Select
          id="rule-severity"
          label={t("rules.sheet.labelSeverity")}
          value={form.severity}
          onChange={(e) => patch({ severity: e.target.value as AlertSeverity })}
          options={SEVERITY_OPTIONS.map((s) => ({
            value: s,
            label: t(`severity.${s}`),
          }))}
          required
        />

        {/* Channels — multi-select via checkboxes */}
        <fieldset>
          <legend className="mb-1.5 block text-sm font-semibold text-[var(--text-primary)]">
            {t("rules.sheet.labelChannels")}
          </legend>
          <div className="flex flex-col gap-2">
            {CHANNEL_OPTIONS.map((ch) => (
              <label
                key={ch}
                className="inline-flex cursor-pointer items-center gap-2"
              >
                <input
                  type="checkbox"
                  checked={form.channels.includes(ch)}
                  onChange={() => toggleChannel(ch)}
                  className="size-4 rounded border-[var(--border-default)] text-[var(--brand-primary)] focus:ring-[var(--brand-primary)]/50"
                />
                <span className="text-sm text-[var(--text-primary)]">
                  {t(`channel.${ch}`)}
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        {/* Enabled */}
        <Switch
          id="rule-enabled"
          checked={form.enabled}
          onCheckedChange={(v) => patch({ enabled: v })}
          label={t("rules.sheet.labelEnabled")}
        />

        <div className="flex items-center justify-end gap-3 pt-2">
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
            disabled={isPending}
          >
            {t("rules.sheet.cancel")}
          </Button>
          <Button type="submit" variant="primary" loading={isPending}>
            {t("rules.sheet.save")}
          </Button>
        </div>
      </form>
    </Sheet>
  );
}

function RulesTab() {
  const t = useTranslations("adminConsole.alerts");
  const toast = useToast();
  const qc = useQueryClient();

  const [sheetOpen, setSheetOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<AlertRule | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AlertRule | null>(null);

  const rulesQuery = useQuery({
    queryKey: ["alerts", "rules"] as const,
    queryFn: () => alertsApi.listRules(),
    staleTime: 60_000,
    retry: 1,
  });

  const rules = rulesQuery.data ?? [];

  // Inline enable toggle
  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      alertsApi.updateRule(id, { enabled }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["alerts", "rules"] });
    },
    onError: () => {
      toast.show({ tone: "error", title: t("rules.sheet.saveError") });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => alertsApi.deleteRule(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["alerts", "rules"] });
      toast.show({ tone: "success", title: t("rules.deleteSuccess") });
      setDeleteTarget(null);
    },
    onError: () => {
      toast.show({ tone: "error", title: t("rules.deleteError") });
    },
  });

  const columns: Column<AlertRule>[] = [
    {
      key: "name",
      header: t("rules.col.name"),
      cell: (row) => (
        <span className="text-sm font-semibold text-[var(--text-primary)]">
          {row.name}
        </span>
      ),
    },
    {
      key: "metric",
      header: t("rules.col.metric"),
      cell: (row) => (
        <span className="text-xs text-[var(--text-secondary)]">
          {t(`metric.${row.metric}`)}
        </span>
      ),
    },
    {
      key: "condition",
      header: t("rules.col.condition"),
      cell: (row) => (
        <span className="font-mono text-xs text-[var(--text-secondary)]">
          {t(`comparison.${row.comparison}`)} {row.threshold}
        </span>
      ),
    },
    {
      key: "severity",
      header: t("rules.col.severity"),
      cell: (row) => (
        <StatusBadge tone={severityTone(row.severity)}>
          {t(`severity.${row.severity}`)}
        </StatusBadge>
      ),
    },
    {
      key: "enabled",
      header: t("rules.col.enabled"),
      cell: (row) => (
        <Switch
          id={`rule-toggle-${row.id}`}
          checked={row.enabled}
          onCheckedChange={(v) =>
            toggleMutation.mutate({ id: row.id, enabled: v })
          }
          label={row.enabled ? t("rules.enabledYes") : t("rules.enabledNo")}
          hideLabel
          disabled={toggleMutation.isPending}
        />
      ),
    },
    {
      key: "channels",
      header: t("rules.col.channels"),
      cell: (row) => (
        <div className="flex flex-wrap gap-1">
          {row.channels.map((ch) => (
            <span
              key={ch}
              className="inline-flex items-center rounded-full border border-[var(--border-subtle)] px-2 py-0.5 text-[0.625rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]"
            >
              {t(`channel.${ch}`)}
            </span>
          ))}
        </div>
      ),
    },
    {
      key: "actions",
      header: t("rules.col.actions"),
      align: "right",
      cell: (row) => (
        <div className="flex items-center justify-end gap-1">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setEditingRule(row);
              setSheetOpen(true);
            }}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/50"
            aria-label={`${t("rules.editAction")} ${row.name}`}
          >
            <PencilSimple aria-hidden className="size-3.5" />
            {t("rules.editAction")}
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setDeleteTarget(row);
            }}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-[var(--brand-red)] transition-colors hover:bg-[var(--red-50)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-red)]/40"
            aria-label={`${t("rules.deleteAction")} ${row.name}`}
          >
            <Trash2 aria-hidden className="size-3.5" />
            {t("rules.deleteAction")}
          </button>
        </div>
      ),
    },
  ];

  function handleAddClick() {
    setEditingRule(null);
    setSheetOpen(true);
  }

  function handleSheetClose() {
    setSheetOpen(false);
    setEditingRule(null);
  }

  if (rulesQuery.isPending) {
    return (
      <div className="marketplace-card rounded-[12px] p-5">
        <RulesPanelHeader onAdd={handleAddClick} />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (rulesQuery.isError) {
    return (
      <div className="marketplace-card rounded-[12px] p-5">
        <RulesPanelHeader onAdd={handleAddClick} />
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("rules.errorTitle")}
          description={t("rules.errorBody")}
          action={
            <button
              onClick={() => void rulesQuery.refetch()}
              className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
            >
              {t("retry")}
            </button>
          }
        />
      </div>
    );
  }

  return (
    <>
      <div className="marketplace-card rounded-[12px] p-5">
        <RulesPanelHeader onAdd={handleAddClick} />
        <DataTable
          columns={columns}
          rows={rules}
          getRowId={(r) => r.id}
          caption={t("tabs.rules")}
          empty={{
            kind: "empty",
            title: t("rules.emptyTitle"),
            description: t("rules.emptyBody"),
          }}
        />
      </div>

      <RuleFormSheet
        open={sheetOpen}
        editing={editingRule}
        onClose={handleSheetClose}
      />

      {/* Delete confirm */}
      <ConfirmDialog
        open={deleteTarget !== null}
        title={t("rules.deleteConfirmTitle")}
        body={t("rules.deleteConfirmBody", {
          name: deleteTarget?.name ?? "",
        })}
        confirmLabel={t("rules.confirm")}
        cancelLabel={t("rules.cancel")}
        onConfirm={() => {
          if (deleteTarget) deleteMutation.mutate(deleteTarget.id);
        }}
        onCancel={() => setDeleteTarget(null)}
        dangerous
        loading={deleteMutation.isPending}
      />
    </>
  );
}

function RulesPanelHeader({ onAdd }: { onAdd: () => void }) {
  const t = useTranslations("adminConsole.alerts");
  return (
    <div className="mb-4 flex items-center justify-between gap-4">
      <h2 className="flex items-center gap-2 text-sm font-bold tracking-tight text-[var(--text-primary)]">
        <span className="icon-chip-primary flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm">
          <Siren aria-hidden className="size-4" />
        </span>
        {t("tabs.rules")}
      </h2>
      <Button variant="primary" onClick={onAdd}>
        <Plus aria-hidden className="size-4" />
        {t("rules.addRule")}
      </Button>
    </div>
  );
}

/* ========================================================================== */
/* Main AlertsScreen                                                           */
/* ========================================================================== */

type TabId = "incidents" | "rules";

export function AlertsScreen() {
  const t = useTranslations("adminConsole.alerts");
  const tabsId = useId();
  const [activeTab, setActiveTab] = useState<TabId>("incidents");

  const tabItems = [
    { value: "incidents", label: t("tabs.incidents") },
    { value: "rules", label: t("tabs.rules") },
  ];

  return (
    <div className="space-y-6">
      <PageHeader title={t("pageTitle")} />

      <Tabs
        items={tabItems}
        value={activeTab}
        onValueChange={(v) => setActiveTab(v as TabId)}
        ariaLabel={t("pageTitle")}
        idBase={tabsId}
      />

      <TabPanel tabsId={tabsId} value="incidents" active={activeTab === "incidents"}>
        <IncidentsTab />
      </TabPanel>
      <TabPanel tabsId={tabsId} value="rules" active={activeTab === "rules"}>
        <RulesTab />
      </TabPanel>
    </div>
  );
}
