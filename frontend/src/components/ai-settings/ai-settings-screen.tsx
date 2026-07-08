"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Brain,
  CheckCircle,
  CloudSlash,
  Cpu,
  CurrencyDollar,
  Key,
  Lightning,
  PauseCircle,
  ShieldWarning,
  SignIn,
  Sliders,
  Warning,
  WarningCircle,
  type Icon,
} from "@phosphor-icons/react";
import Link from "next/link";
import {
  Button,
  EmptyState,
  Input,
  Modal,
  Select,
  StatusBadge,
  Switch,
  useToast,
  type StatusTone,
} from "@/components/ui";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/layout/page-header";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import {
  ApiError,
  aiSettingsApi,
  AI_MODEL_FAMILIES,
  AI_ROLLOUT_STATES,
  AI_ALIAS_FIELD,
  type AiModelFamily,
  type AiRealCallsStatus,
  type AiRolloutState,
  type AiSettings,
  type AiSettingsUpdateBody,
} from "@/lib/api";
import { AiProviderManager } from "./ai-provider-manager";

/* ---- Derived-status presentation (text + icon, never color-only) ---- */
const STATUS_TONE: Record<AiRealCallsStatus, StatusTone> = {
  enabled: "active",
  available: "pending",
  offline: "closed",
};
const STATUS_ICON: Record<AiRealCallsStatus, typeof CheckCircle> = {
  enabled: CheckCircle,
  available: PauseCircle,
  offline: CloudSlash,
};
const STATUS_LABEL_KEY: Record<AiRealCallsStatus, string> = {
  enabled: "statusEnabled",
  available: "statusAvailable",
  offline: "statusOffline",
};

interface Draft {
  models: Record<AiModelFamily, string>;
  cv_llm_structuring_enabled: boolean;
  job_fit_ai_explanation_enabled: boolean;
  real_calls_enabled: boolean;
  rollout_state: AiRolloutState;
  /** Editable string mirror of `daily_budget_usd`. */
  budget: string;
}

function toDraft(s: AiSettings): Draft {
  return {
    models: { ...s.models },
    cv_llm_structuring_enabled: s.feature_flags.cv_llm_structuring_enabled,
    job_fit_ai_explanation_enabled: s.feature_flags.job_fit_ai_explanation_enabled,
    real_calls_enabled: s.real_calls_enabled,
    rollout_state: s.rollout_state,
    budget: s.daily_budget_usd,
  };
}

export function AiSettingsScreen() {
  const t = useTranslations("aiSettings");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const query = useQuery({
    queryKey: ["admin", "ai-settings"],
    queryFn: () => aiSettingsApi.get(),
    retry: false,
  });

  const [draft, setDraft] = useState<Draft | null>(null);
  const [budgetError, setBudgetError] = useState<string | null>(null);
  const [killOpen, setKillOpen] = useState(false);
  const [killReason, setKillReason] = useState("");
  const appliedVersion = useRef<number | null>(null);

  // Sync server data into the editable draft when a new version arrives (does
  // not clobber in-flight edits of the same version).
  useEffect(() => {
    const data = query.data;
    if (!data) return;
    if (appliedVersion.current !== data.version) {
      appliedVersion.current = data.version;
      setDraft(toDraft(data));
      setBudgetError(null);
    }
  }, [query.data]);

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["admin", "ai-settings"] });
  }

  function handleError(e: unknown) {
    if (e instanceof ApiError && e.isConflict) {
      toast.show({
        tone: "error",
        title: t("conflictTitle"),
        description: t("conflictBody"),
      });
      appliedVersion.current = null; // force re-sync on next fetch
      refresh();
      return;
    }
    toast.show({ tone: "error", title: getMessage(e) });
  }

  const save = useMutation({
    mutationFn: (body: AiSettingsUpdateBody) => aiSettingsApi.update(body),
    onSuccess: (updated) => {
      appliedVersion.current = updated.version;
      setDraft(toDraft(updated));
      setBudgetError(null);
      qc.setQueryData(["admin", "ai-settings"], updated);
      toast.show({ tone: "success", title: t("savedToast") });
    },
    onError: handleError,
  });

  const disable = useMutation({
    mutationFn: (reason: string | undefined) => aiSettingsApi.disable(reason),
    onSuccess: (updated) => {
      appliedVersion.current = updated.version;
      setDraft(toDraft(updated));
      setKillOpen(false);
      setKillReason("");
      qc.setQueryData(["admin", "ai-settings"], updated);
      toast.show({ tone: "success", title: t("killedToast") });
    },
    onError: (e) => {
      setKillOpen(false);
      handleError(e);
    },
  });

  /* ---- Permission / auth states ---- */
  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError || err.isNotFound) {
      const isAuth = err.isAuthError;
      return (
        <>
          <PageHeader title={t("title")} description={t("subtitle")} />
          <EmptyState
            kind={isAuth ? "auth" : "permission"}
            icon={isAuth ? SignIn : ShieldWarning}
            title={isAuth ? tStates("authTitle") : tStates("permissionTitle")}
            description={isAuth ? tStates("authBody") : t("permissionBody")}
          />
        </>
      );
    }
  }

  /* ---- Generic load error ---- */
  if (query.isError) {
    return (
      <>
        <PageHeader title={t("title")} description={t("subtitle")} />
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

  const data = query.data;

  /* ---- Loading skeleton ---- */
  if (!data || !draft) {
    return (
      <>
        <PageHeader title={t("title")} description={t("subtitle")} />
        <div className="space-y-4" aria-busy="true">
          {[0, 1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-32 animate-pulse rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-subtle)]"
            />
          ))}
        </div>
      </>
    );
  }

  /* ---- Dirty detection + patch body ---- */
  function buildPatch(): AiSettingsUpdateBody | null {
    if (!data || !draft) return null;
    const body: AiSettingsUpdateBody = {};
    for (const family of AI_MODEL_FAMILIES) {
      if (draft.models[family] !== data.models[family]) {
        body[AI_ALIAS_FIELD[family]] = draft.models[family] as never;
      }
    }
    if (draft.cv_llm_structuring_enabled !== data.feature_flags.cv_llm_structuring_enabled) {
      body.cv_llm_structuring_enabled = draft.cv_llm_structuring_enabled;
    }
    if (
      draft.job_fit_ai_explanation_enabled !==
      data.feature_flags.job_fit_ai_explanation_enabled
    ) {
      body.job_fit_ai_explanation_enabled = draft.job_fit_ai_explanation_enabled;
    }
    if (draft.real_calls_enabled !== data.real_calls_enabled) {
      body.real_calls_enabled = draft.real_calls_enabled;
    }
    if (draft.rollout_state !== data.rollout_state) {
      body.rollout_state = draft.rollout_state;
    }
    const draftBudget = Number.parseFloat(draft.budget);
    const serverBudget = Number.parseFloat(data.daily_budget_usd);
    if (Number.isFinite(draftBudget) && draftBudget !== serverBudget) {
      body.daily_budget_usd = draftBudget;
    }
    return Object.keys(body).length > 0 ? body : null;
  }

  function validateBudget(): boolean {
    if (!draft) return false;
    const n = Number.parseFloat(draft.budget);
    if (!Number.isFinite(n) || n < 0 || n > 10000) {
      setBudgetError(t("budgetInvalid"));
      return false;
    }
    setBudgetError(null);
    return true;
  }

  function onSave() {
    if (!validateBudget()) return;
    const body = buildPatch();
    if (!body) {
      toast.show({ tone: "info", title: t("noChanges") });
      return;
    }
    save.mutate(body);
  }

  const dirty = buildPatch() !== null;
  const StatusIcon = STATUS_ICON[data.real_calls];

  function whyCopy(): string {
    if (data!.real_calls === "enabled") return t("whyEnabled");
    if (data!.real_calls === "available") return t("whyAvailable");
    return data!.key_configured ? t("whyOfflineEnvBlocked") : t("whyOfflineNoKey");
  }

  function patchDraft(p: Partial<Draft>) {
    setDraft((d) => (d ? { ...d, ...p } : d));
  }

  return (
    <>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          <>
            <Link href="/university/ai-settings/routing">
              <Button variant="secondary">{t("routingLinkLabel")}</Button>
            </Link>
            <Button
              variant="danger"
              onClick={() => {
                setKillReason("");
                setKillOpen(true);
              }}
            >
              <Warning aria-hidden weight="bold" className="size-4" />
              {t("killSwitch")}
            </Button>
          </>
        }
      />

      <div className="space-y-4">
        {/* Status panel */}
        <section className="rounded-2xl border border-white/60 bg-white/82 p-5 backdrop-blur-md shadow-[0_2px_12px_rgba(11,34,57,0.06)]">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <div className="mb-3 flex items-center gap-2.5">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-lg icon-chip-info shadow-sm">
                  <Brain aria-hidden weight="duotone" className="size-4 text-white" />
                </span>
                <h2 className="text-base font-bold text-[var(--text-primary)]">
                  {t("statusTitle")}
                </h2>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge tone={STATUS_TONE[data.real_calls]}>
                  <StatusIcon aria-hidden weight="bold" className="size-3.5" />
                  {t(STATUS_LABEL_KEY[data.real_calls])}
                </StatusBadge>
                <span className="inline-flex items-center gap-1.5 rounded-full border border-white/60 bg-white/75 px-2.5 py-0.5 text-xs font-semibold text-[var(--text-secondary)] backdrop-blur-sm">
                  <Key aria-hidden weight="bold" className="size-3.5" />
                  {t("keyIndicatorLabel")}:{" "}
                  <span
                    className={
                      data.key_configured
                        ? "text-[var(--teal-600)]"
                        : "text-[var(--text-muted)]"
                    }
                  >
                    {data.key_configured ? t("keyConfigured") : t("keyMissing")}
                  </span>
                </span>
              </div>
              <p className="mt-2 max-w-2xl text-sm text-[var(--text-secondary)]">
                {whyCopy()}
              </p>
            </div>
          </div>
        </section>

        {/* Model aliases */}
        <Card
          title={t("modelsTitle")}
          subtitle={t("modelsSubtitle")}
          icon={Cpu}
          iconGradient="icon-chip-primary"
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {AI_MODEL_FAMILIES.map((family) => {
              const options = data.allowed_aliases[family] ?? [];
              return (
                <Select
                  key={family}
                  id={`ai-alias-${family}`}
                  label={t(`family.${family}`)}
                  value={draft.models[family]}
                  help={t("aliasHelp")}
                  onChange={(e) =>
                    patchDraft({
                      models: { ...draft.models, [family]: e.target.value },
                    })
                  }
                  options={options.map((alias) => ({
                    value: alias,
                    label: alias,
                  }))}
                />
              );
            })}
          </div>
        </Card>

        {/* Feature flags */}
        <Card
          title={t("flagsTitle")}
          subtitle={t("flagsSubtitle")}
          icon={Sliders}
          iconGradient="icon-chip-success"
        >
          <div className="space-y-4">
            <ToggleRow
              id="ai-flag-cv"
              label={t("cvStructuringLabel")}
              help={t("cvStructuringHelp")}
              checked={draft.cv_llm_structuring_enabled}
              onChange={(v) => patchDraft({ cv_llm_structuring_enabled: v })}
            />
            <ToggleRow
              id="ai-flag-jobfit"
              label={t("jobFitLabel")}
              help={t("jobFitHelp")}
              checked={draft.job_fit_ai_explanation_enabled}
              onChange={(v) => patchDraft({ job_fit_ai_explanation_enabled: v })}
            />
          </div>
        </Card>

        {/* Activation & rollout */}
        <Card
          title={t("activationTitle")}
          subtitle={t("activationSubtitle")}
          icon={Lightning}
          iconGradient="icon-chip-warning"
        >
          <div className="space-y-4">
            <ToggleRow
              id="ai-real-calls"
              label={t("realCallsLabel")}
              help={t("realCallsHelp")}
              checked={draft.real_calls_enabled}
              onChange={(v) => patchDraft({ real_calls_enabled: v })}
            />
            <div className="max-w-xs">
              <Select
                id="ai-rollout"
                label={t("rolloutLabel")}
                value={draft.rollout_state}
                help={t("rolloutHelp")}
                onChange={(e) =>
                  patchDraft({ rollout_state: e.target.value as AiRolloutState })
                }
                options={AI_ROLLOUT_STATES.map((s) => ({
                  value: s,
                  label: t(`rollout.${s}`),
                }))}
              />
            </div>
          </div>
        </Card>

        {/* Budget */}
        <Card
          title={t("budgetTitle")}
          icon={CurrencyDollar}
          iconGradient="icon-chip-success"
        >
          <div className="max-w-xs">
            <Input
              id="ai-budget"
              type="number"
              inputMode="decimal"
              min={0}
              max={10000}
              step="0.5"
              label={t("budgetLabel")}
              value={draft.budget}
              error={budgetError ?? undefined}
              help={t("budgetHelp")}
              onChange={(e) => {
                patchDraft({ budget: e.target.value });
                if (budgetError) setBudgetError(null);
              }}
            />
          </div>
        </Card>

        {/* Multi-provider configuration */}
        <AiProviderManager />

        {/* Secrecy footnote */}
        <p className="px-1 text-xs text-[var(--text-muted)]">{t("secrecyNote")}</p>

        {/* Save bar */}
        <div className="sticky bottom-0 -mx-1 flex items-center justify-between gap-3 border-t border-white/40 bg-[var(--bg-base)]/90 px-1 py-3 backdrop-blur">
          <span className="text-xs text-[var(--text-muted)]">
            {data.updated_at
              ? `${t("updatedAt")}: ${new Date(data.updated_at).toLocaleString()}`
              : ""}
          </span>
          <Button
            variant="primary"
            disabled={!dirty}
            loading={save.isPending}
            onClick={onSave}
          >
            {t("save")}
          </Button>
        </div>
      </div>

      {/* Kill switch — focus-trapped modal (never confirm()) */}
      <Modal
        open={killOpen}
        onClose={() => setKillOpen(false)}
        title={t("killTitle")}
        description={t("killBody")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setKillOpen(false)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="danger"
              loading={disable.isPending}
              onClick={() => disable.mutate(killReason.trim() || undefined)}
            >
              <Warning aria-hidden weight="bold" className="size-4" />
              {t("killConfirm")}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <div className="flex items-start gap-2 rounded-xl bg-[var(--red-50)] px-3 py-2.5 text-sm text-[var(--brand-red)]">
            <span className="flex size-5 shrink-0 items-center justify-center rounded-md icon-chip-danger shadow-sm">
              <Warning aria-hidden weight="fill" className="size-3 text-white" />
            </span>
            <p>{t("killNote")}</p>
          </div>
          <div>
            <label
              htmlFor="ai-kill-reason"
              className="mb-1.5 block text-sm font-semibold text-[var(--text-primary)]"
            >
              {t("killReasonLabel")}
            </label>
            <textarea
              id="ai-kill-reason"
              rows={3}
              value={killReason}
              onChange={(e) => setKillReason(e.target.value)}
              className="w-full rounded-xl border border-white/60 bg-white/80 backdrop-blur-sm px-3.5 py-2.5 text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand-primary)]/50 focus:bg-white/95 focus:ring-2 focus:ring-[var(--brand-primary)]/30"
            />
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              {t("killReasonHint")}
            </p>
          </div>
        </div>
      </Modal>
    </>
  );
}

function Card({
  title,
  subtitle,
  icon: IconCmp,
  iconGradient,
  children,
}: {
  title: string;
  subtitle?: string;
  icon?: Icon;
  iconGradient?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-white/60 bg-white/82 p-5 backdrop-blur-md shadow-[0_2px_12px_rgba(11,34,57,0.06)]">
      <div className="mb-4 flex items-start gap-2.5">
        {IconCmp && iconGradient && (
          <span
            className={cn(
              "flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm",
              iconGradient,
            )}
          >
            <IconCmp aria-hidden weight="duotone" className="size-4 text-white" />
          </span>
        )}
        <div className="min-w-0">
          <h2 className="text-base font-bold text-[var(--text-primary)]">{title}</h2>
          {subtitle && (
            <p className="mt-0.5 text-sm text-[var(--text-secondary)]">{subtitle}</p>
          )}
        </div>
      </div>
      {children}
    </section>
  );
}

function ToggleRow({
  id,
  label,
  help,
  checked,
  onChange,
}: {
  id: string;
  label: string;
  help: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <label
          htmlFor={id}
          className="block text-sm font-semibold text-[var(--text-primary)]"
        >
          {label}
        </label>
        <p className="mt-0.5 text-xs text-[var(--text-secondary)]">{help}</p>
      </div>
      <div className="shrink-0 pt-0.5">
        <Switch checked={checked} onCheckedChange={onChange} label={label} hideLabel id={id} />
      </div>
    </div>
  );
}
