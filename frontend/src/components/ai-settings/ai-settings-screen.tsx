"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Brain,
  CheckCircle2,
  CloudOff,
  Cpu,
  DollarSign,
  KeyRound,
  Network,
  PauseCircle,
  ShieldCheck,
  SlidersHorizontal,
  TriangleAlert,
  Zap,
} from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Button, Input, Modal, Select, Switch, useToast } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  KpiRow,
  KpiTile,
  StatusChip,
  type ChipTone,
} from "@/components/kit";
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
const STATUS_TONE: Record<AiRealCallsStatus, ChipTone> = {
  enabled: "success",
  available: "warning",
  offline: "neutral",
};
const STATUS_ICON: Record<AiRealCallsStatus, React.ElementType> = {
  enabled: CheckCircle2,
  available: PauseCircle,
  offline: CloudOff,
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

  const [draft, setDraft] = React.useState<Draft | null>(null);
  const [budgetError, setBudgetError] = React.useState<string | null>(null);
  const [killOpen, setKillOpen] = React.useState(false);
  const [killReason, setKillReason] = React.useState("");
  const appliedVersion = React.useRef<number | null>(null);

  // Sync server data into the editable draft when a new version arrives.
  React.useEffect(() => {
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
      toast.show({ tone: "error", title: t("conflictTitle"), description: t("conflictBody") });
      appliedVersion.current = null;
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

  const header = (
    <PageHeader
      title={t("title")}
      subtitle={t("subtitle")}
      actions={
        <>
          <Link href="/university/ai-settings/routing">
            <Button variant="secondary" size="sm">
              <Network className="size-4" strokeWidth={1.8} />
              {t("routingLinkLabel")}
            </Button>
          </Link>
          <Button
            variant="danger"
            size="sm"
            onClick={() => {
              setKillReason("");
              setKillOpen(true);
            }}
          >
            <TriangleAlert className="size-4" strokeWidth={2} />
            {t("killSwitch")}
          </Button>
        </>
      }
    />
  );

  /* ---- Permission / auth / not-found states ---- */
  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError || err.isNotFound) {
      const isAuth = err.isAuthError;
      return (
        <>
          {header}
          <EmptyState
            kind={isAuth ? "auth" : "permission"}
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
        {header}
        <EmptyState
          kind="error"
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
        {header}
        <div className="space-y-4" aria-busy="true">
          <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-[86px] animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
            ))}
          </div>
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-40 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
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
    if (draft.job_fit_ai_explanation_enabled !== data.feature_flags.job_fit_ai_explanation_enabled) {
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

  const perOrgCap =
    data.per_org_daily_budget_usd != null ? `$${data.per_org_daily_budget_usd}` : t("perOrgBudgetNone");

  return (
    <>
      {header}

      <div className="space-y-4">
        {/* Governance KPI row (masked — no provider/model/key) */}
        <KpiRow cols={4}>
          <KpiTile label={t("statusTitle")} value={t(STATUS_LABEL_KEY[data.real_calls])} icon={StatusIcon} />
          <KpiTile label={t("budgetLabel")} value={`$${data.daily_budget_usd}`} icon={DollarSign} />
          <KpiTile label={t("rolloutLabel")} value={t(`rollout.${data.rollout_state}`)} icon={Zap} />
          <KpiTile
            label={t("keyIndicatorLabel")}
            value={data.key_configured ? t("keyConfigured") : t("keyMissing")}
            icon={KeyRound}
          />
        </KpiRow>

        {/* Status card */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2.5">
              <span
                className="flex size-8 items-center justify-center rounded-lg"
                style={{ background: "var(--content-ai-soft)" }}
              >
                <Brain className="size-4" strokeWidth={1.9} style={{ color: "var(--content-ai)" }} />
              </span>
              <CardTitle>{t("statusTitle")}</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-center gap-2">
              <StatusChip tone={STATUS_TONE[data.real_calls]} dot>
                <StatusIcon aria-hidden className="size-3.5" strokeWidth={2} />
                {t(STATUS_LABEL_KEY[data.real_calls])}
              </StatusChip>
              <StatusChip tone={data.key_configured ? "success" : "neutral"}>
                <KeyRound aria-hidden className="size-3.5" strokeWidth={2} />
                {t("keyIndicatorLabel")}: {data.key_configured ? t("keyConfigured") : t("keyMissing")}
              </StatusChip>
            </div>
            <p className="mt-3 max-w-2xl type-small text-muted-foreground">{whyCopy()}</p>
          </CardContent>
        </Card>

        {/* Model aliases */}
        <SettingsCard title={t("modelsTitle")} subtitle={t("modelsSubtitle")} icon={Cpu}>
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
                  onChange={(e) => patchDraft({ models: { ...draft.models, [family]: e.target.value } })}
                  options={options.map((alias) => ({ value: alias, label: alias }))}
                />
              );
            })}
          </div>
        </SettingsCard>

        {/* Feature flags */}
        <SettingsCard title={t("flagsTitle")} subtitle={t("flagsSubtitle")} icon={SlidersHorizontal}>
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
        </SettingsCard>

        {/* Activation & rollout */}
        <SettingsCard title={t("activationTitle")} subtitle={t("activationSubtitle")} icon={Zap}>
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
                onChange={(e) => patchDraft({ rollout_state: e.target.value as AiRolloutState })}
                options={AI_ROLLOUT_STATES.map((s) => ({ value: s, label: t(`rollout.${s}`) }))}
              />
            </div>
          </div>
        </SettingsCard>

        {/* Budget */}
        <SettingsCard title={t("budgetTitle")} icon={DollarSign}>
          <div className="grid gap-4 sm:grid-cols-2">
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
            <div>
              <p className="mb-1.5 block text-sm font-semibold text-foreground">{t("perOrgBudgetLabel")}</p>
              <div className="flex h-[42px] items-center rounded-xl border border-border bg-[var(--bg-subtle)] px-3.5 text-sm font-semibold tabular-nums text-foreground">
                {perOrgCap}
              </div>
              <p className="mt-1 type-caption text-muted-foreground">{t("perOrgBudgetHelp")}</p>
            </div>
          </div>
        </SettingsCard>

        {/* Multi-provider registry (superadmin-only; RBAC-gated component) */}
        <AiProviderManager />

        {/* Secrecy footnote */}
        <p className="flex items-start gap-2 px-1 type-caption text-muted-foreground">
          <ShieldCheck aria-hidden className="mt-0.5 size-3.5 shrink-0" strokeWidth={1.8} />
          {t("secrecyNote")}
        </p>

        {/* Save bar */}
        <div className="sticky bottom-0 -mx-1 flex items-center justify-between gap-3 border-t border-border bg-[var(--bg-base)]/90 px-1 py-3 backdrop-blur">
          <span className="type-caption text-muted-foreground">
            {data.updated_at ? `${t("updatedAt")}: ${new Date(data.updated_at).toLocaleString()}` : ""}
          </span>
          <Button variant="primary" disabled={!dirty} loading={save.isPending} onClick={onSave}>
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
              <TriangleAlert className="size-4" strokeWidth={2} />
              {t("killConfirm")}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <div
            className="flex items-start gap-2 rounded-xl px-3 py-2.5 text-sm"
            style={{ background: "var(--content-danger-soft)", color: "var(--content-danger)" }}
          >
            <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" strokeWidth={2} />
            <p>{t("killNote")}</p>
          </div>
          <div>
            <label htmlFor="ai-kill-reason" className="mb-1.5 block text-sm font-semibold text-foreground">
              {t("killReasonLabel")}
            </label>
            <textarea
              id="ai-kill-reason"
              rows={3}
              value={killReason}
              onChange={(e) => setKillReason(e.target.value)}
              className="w-full rounded-xl border border-border bg-card px-3.5 py-2.5 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-[var(--field-focus-border)] focus:ring-2 focus:ring-[var(--field-focus-border)]"
            />
            <p className="mt-1 type-caption text-muted-foreground">{t("killReasonHint")}</p>
          </div>
        </div>
      </Modal>
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Section card + toggle row                                                    */
/* -------------------------------------------------------------------------- */

function SettingsCard({
  title,
  subtitle,
  icon: Icon,
  children,
}: {
  title: string;
  subtitle?: string;
  icon: React.ElementType;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start gap-2.5">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-[var(--bg-muted)] text-muted-foreground">
            <Icon className="size-4" strokeWidth={1.8} />
          </span>
          <div className="min-w-0">
            <CardTitle>{title}</CardTitle>
            {subtitle && <CardDescription>{subtitle}</CardDescription>}
          </div>
        </div>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
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
        <label htmlFor={id} className="block text-sm font-semibold text-foreground">
          {label}
        </label>
        <p className="mt-0.5 type-caption text-muted-foreground">{help}</p>
      </div>
      <div className="shrink-0 pt-0.5">
        <Switch checked={checked} onCheckedChange={onChange} label={label} hideLabel id={id} />
      </div>
    </div>
  );
}
