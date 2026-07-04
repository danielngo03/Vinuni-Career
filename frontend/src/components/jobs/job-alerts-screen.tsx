"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { BellSimple, BellSimpleSlash, LightbulbFilament, Plus, Sparkle, Trash, WarningCircle } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import {
  Button,
  EmptyState,
  Input,
  Modal,
  Select,
  Skeleton,
  useToast,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import {
  ApiError,
  jobAlertsApi,
  EMPLOYMENT_TYPES,
  LOCATION_TYPES,
  type JobAlert,
  type CreateJobAlertBody,
} from "@/lib/api";

export function JobAlertsScreen() {
  const t = useTranslations("jobs.alerts");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const toast = useToast();
  const qc = useQueryClient();

  const [showForm, setShowForm] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<JobAlert | null>(null);

  const query = useQuery({
    queryKey: ["job-alerts"],
    queryFn: () => jobAlertsApi.list(),
    retry: false,
  });

  const alerts = query.data ?? [];
  const atLimit = alerts.length >= 10;

  const createMutation = useMutation({
    mutationFn: (body: CreateJobAlertBody) => jobAlertsApi.create(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["job-alerts"] });
      setShowForm(false);
      toast.show({ tone: "success", title: t("createdToast") });
    },
    onError: (err) => {
      const msg =
        err instanceof ApiError && err.code === "CONFLICT"
          ? t("nameConflict")
          : t("createError");
      toast.show({ tone: "error", title: msg });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (alertId: string) => jobAlertsApi.delete(alertId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["job-alerts"] });
      setDeleteTarget(null);
      toast.show({ tone: "success", title: t("deleteToast") });
    },
    onError: () => {
      toast.show({ tone: "error", title: t("deleteError") });
    },
  });

  return (
    <>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          !atLimit && (
            <Button variant="primary" size="sm" onClick={() => setShowForm(true)}>
              <Plus weight="bold" className="size-3.5" />
              {t("newAlertCta")}
            </Button>
          )
        }
      />

      {query.isLoading ? (
        <div className="space-y-3 px-4 py-6">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20 rounded-2xl" />
          ))}
        </div>
      ) : query.isError ? (
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
      ) : alerts.length === 0 ? (
        <EmptyState
          kind="empty"
          icon={BellSimpleSlash}
          title={t("empty")}
          description={t("emptyBody")}
          action={
            <Button variant="primary" onClick={() => setShowForm(true)}>
              <Plus weight="bold" className="size-4" />
              {t("newAlertCta")}
            </Button>
          }
        />
      ) : (
        <div className="space-y-3 px-4 py-6">
          {atLimit && (
            <p className="rounded-xl border border-[var(--amber-100)] bg-[var(--amber-50)]/60 px-4 py-3 text-sm text-[var(--amber-700)]">
              {t("limitReached")}
            </p>
          )}

          {/* AI Alert Intelligence panel */}
          {(() => {
            const activeCount = alerts.filter((a) => a.is_active).length;
            const now = Date.now();
            const recentAlert = alerts
              .filter((a) => a.last_sent_at)
              .sort((a, b) => new Date(b.last_sent_at!).getTime() - new Date(a.last_sent_at!).getTime())[0];
            const recentDays = recentAlert?.last_sent_at
              ? Math.floor((now - new Date(recentAlert.last_sent_at).getTime()) / 86_400_000)
              : null;
            const broadAlerts = alerts.filter(
              (a) => !a.keywords && !a.employment_type && !a.location_type,
            ).length;
            const insights: string[] = [];
            insights.push(t("aiInsightTotal", { count: alerts.length, active: activeCount }));
            if (recentDays !== null && recentDays <= 7) {
              insights.push(t("aiInsightRecent", { days: recentDays }));
            } else if (recentDays === null || recentDays > 14) {
              insights.push(t("aiInsightNoRecent"));
            }
            if (broadAlerts > 0) insights.push(t("aiInsightBroad", { count: broadAlerts }));
            return (
              <div className={cn(
                "rounded-2xl border p-4",
                "border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-[var(--glass-surface-light)] backdrop-blur-xl",
              )}>
                <p className="mb-2.5 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-info shadow-sm">
                    <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
                  </span>
                  {t("aiInsightsTitle")}
                </p>
                <ul className="space-y-1.5">
                  {insights.map((text, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                      <LightbulbFilament aria-hidden weight="duotone" className="mt-px size-3.5 shrink-0 text-[var(--ai-accent)]" />
                      {text}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })()}

          {alerts.map((alert) => (
            <AlertCard
              key={alert.id}
              alert={alert}
              onDelete={() => setDeleteTarget(alert)}
            />
          ))}
        </div>
      )}

      <CreateAlertModal
        open={showForm}
        onClose={() => setShowForm(false)}
        onSubmit={(body) => createMutation.mutate(body)}
        loading={createMutation.isPending}
      />

      <Modal
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        title={t("deleteTitle")}
        description={t("deleteBody")}
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="danger"
              loading={deleteMutation.isPending}
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
            >
              {t("deleteConfirm")}
            </Button>
          </div>
        }
      >
        <span />
      </Modal>
    </>
  );
}

function AlertCard({
  alert,
  onDelete,
}: {
  alert: JobAlert;
  onDelete: () => void;
}) {
  const t = useTranslations("jobs.alerts");

  const chips: string[] = [];
  if (alert.keywords) chips.push(alert.keywords);
  if (alert.employment_type) chips.push(alert.employment_type.replace("_", " "));
  if (alert.location_type) chips.push(alert.location_type);
  if (alert.province_code) chips.push(alert.province_code);

  const lastSentLabel = alert.last_sent_at
    ? t("lastSent", {
        date: new Date(alert.last_sent_at).toLocaleDateString("vi-VN", {
          day: "numeric",
          month: "short",
        }),
      })
    : t("neverSent");

  return (
    <div className="flex items-start gap-3 rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-4 shadow-sm backdrop-blur-md">
      <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-xl icon-chip-primary shadow-sm">
        <BellSimple weight="duotone" className="size-4 text-white" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate font-semibold text-[var(--text-primary)]">{alert.name}</p>
        {chips.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {chips.map((chip) => (
              <span
                key={chip}
                className="rounded-full bg-[var(--surface-secondary)] px-2 py-0.5 text-[11px] capitalize text-[var(--text-muted)]"
              >
                {chip}
              </span>
            ))}
          </div>
        )}
        <p className="mt-2 text-[11px] text-[var(--text-muted)]">{lastSentLabel}</p>
      </div>
      <button
        aria-label={t("deleteAlert")}
        onClick={onDelete}
        className="ml-1 rounded-lg p-1.5 text-[var(--text-muted)] transition-colors hover:bg-[var(--red-50)] hover:text-[var(--red-600)]"
      >
        <Trash className="size-4" />
      </button>
    </div>
  );
}

function CreateAlertModal({
  open,
  onClose,
  onSubmit,
  loading,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (body: CreateJobAlertBody) => void;
  loading: boolean;
}) {
  const t = useTranslations("jobs.alerts");
  const [name, setName] = useState("");
  const [keywords, setKeywords] = useState("");
  const [employmentType, setEmploymentType] = useState("");
  const [locationType, setLocationType] = useState("");

  const employmentOptions = [
    { label: t("allTypes"), value: "" },
    ...EMPLOYMENT_TYPES.map((v) => ({
      label: v.replace("_", " "),
      value: v,
    })),
  ];

  const locationOptions = [
    { label: t("allModes"), value: "" },
    ...LOCATION_TYPES.map((v) => ({ label: v, value: v })),
  ];

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    onSubmit({
      name: name.trim(),
      keywords: keywords.trim() || null,
      employment_type: employmentType || null,
      location_type: locationType || null,
    });
  }

  function handleClose() {
    if (loading) return;
    setName("");
    setKeywords("");
    setEmploymentType("");
    setLocationType("");
    onClose();
  }

  return (
    <Modal open={open} onClose={handleClose} title={t("newAlertCta")}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label={t("nameLabel")}
          placeholder={t("namePlaceholder")}
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          autoFocus
        />
        <Input
          label={t("keywordsLabel")}
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
        />
        <Select
          label={t("employmentTypeLabel")}
          value={employmentType}
          onChange={(e) => setEmploymentType(e.target.value)}
          options={employmentOptions}
        />
        <Select
          label={t("locationTypeLabel")}
          value={locationType}
          onChange={(e) => setLocationType(e.target.value)}
          options={locationOptions}
        />
        <p className="text-[11px] text-[var(--text-muted)]">{t("disclaimer")}</p>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" type="button" onClick={handleClose} disabled={loading}>
            {t("cancelCta")}
          </Button>
          <Button variant="primary" type="submit" loading={loading} disabled={!name.trim()}>
            {loading ? t("creating") : t("createCta")}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
