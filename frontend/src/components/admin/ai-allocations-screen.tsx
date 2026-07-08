"use client";

import { useId, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Lightning,
  Buildings,
  UsersThree,
  User,
  WarningCircle,
  PencilSimple,
  ShieldWarning,
} from "@phosphor-icons/react";
import {
  Tabs,
  TabPanel,
  DataTable,
  Modal,
  Input,
  Textarea,
  Button,
  SegmentedControl,
  StatusBadge,
  EmptyState,
  Skeleton,
  useToast,
  type Column,
  type TabItem,
} from "@/components/ui";
import {
  aiGovernanceApi,
  ApiError,
  type AiAllocations,
  type AiAllocationDepartmentNode,
  type AiAllocationMemberNode,
  type AiCapacityRequestQueueItem,
  type AllocationScopeType,
  type CapacityRequestStatus,
} from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import {
  capacityStatusTone,
  formatCredits,
  formatDate,
  formatDateTime,
} from "@/components/ai-governance/helpers";
import { cn } from "@/lib/utils";

/* -------------------------------------------------------------------------- */
/* Energy bar cell — remaining %, paired with a numeric label (never color-only) */
/* -------------------------------------------------------------------------- */

function EnergyCell({
  pct,
  inheritedLabel,
}: {
  pct: number | null;
  inheritedLabel: string;
}) {
  const t = useTranslations("adminConsole.aiDistribution.energy");
  if (pct == null) {
    return (
      <span className="text-xs text-[var(--text-muted)]">{inheritedLabel}</span>
    );
  }
  const clamped = Math.min(100, Math.max(0, pct));
  const tone =
    clamped <= 0
      ? "bg-[var(--red-600)]"
      : clamped < 20
        ? "bg-[var(--amber-500)]"
        : "bg-[var(--text-primary)]";
  const textTone =
    clamped <= 0
      ? "text-[var(--red-600)]"
      : clamped < 20
        ? "text-[var(--amber-700)]"
        : "text-[var(--text-secondary)]";
  return (
    <div className="flex items-center gap-2">
      <div
        role="meter"
        aria-valuenow={Math.round(clamped)}
        aria-valuemin={0}
        aria-valuemax={100}
        className="h-1.5 w-16 shrink-0 overflow-hidden rounded-full bg-[var(--bg-muted)]"
      >
        <div
          className={cn("h-full rounded-full", tone)}
          style={{ width: `${clamped}%` }}
        />
      </div>
      <span className={cn("text-xs font-semibold tabular-nums", textTone)}>
        {t("value", { pct: Math.round(clamped) })}
      </span>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Set-ceiling dialog                                                          */
/* -------------------------------------------------------------------------- */

interface CeilingTarget {
  scopeType: AllocationScopeType;
  scopeId: string;
  name: string;
  currentCeiling: number | null;
}

function SetCeilingDialog({
  target,
  orgId,
  onClose,
}: {
  target: CeilingTarget | null;
  orgId: string;
  onClose: () => void;
}) {
  const t = useTranslations("adminConsole.aiDistribution.ceiling");
  const toast = useToast();
  const qc = useQueryClient();

  const [mode, setMode] = useState<"explicit" | "inherit">("explicit");
  const [units, setUnits] = useState("");
  const [unitsError, setUnitsError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  // Re-seed the form whenever a new target opens; clear the seed on close so
  // reopening the same row starts fresh (derived-state-from-props pattern).
  const [seededId, setSeededId] = useState<string | null>(null);
  if (target && seededId !== target.scopeId) {
    setSeededId(target.scopeId);
    setMode(target.currentCeiling == null ? "inherit" : "explicit");
    setUnits(target.currentCeiling == null ? "" : String(target.currentCeiling));
    setUnitsError(null);
    setFormError(null);
  } else if (!target && seededId !== null) {
    setSeededId(null);
  }

  const mutation = useMutation({
    mutationFn: () => {
      if (!target) throw new Error("no target");
      const value =
        mode === "inherit" ? null : Math.round(Number(units));
      return aiGovernanceApi.upsertAllocation({
        scope_type: target.scopeType,
        scope_id: target.scopeId,
        org_id: orgId,
        weekly_allowance_units: value,
      });
    },
    onSuccess: () => {
      void qc.invalidateQueries({
        queryKey: ["ai-governance", "allocations", orgId],
      });
      toast.show({ tone: "success", title: t("savedToast") });
      onClose();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.isValidation) {
        setFormError(e.message || t("errorToast"));
        return;
      }
      setFormError(t("errorToast"));
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (mode === "explicit") {
      const n = Number(units);
      if (units.trim() === "" || !Number.isInteger(n) || n < 0 || n > 1_000_000) {
        setUnitsError(t("unitsInvalid"));
        return;
      }
    }
    mutation.mutate();
  }

  const dialogTitle =
    target?.scopeType === "org"
      ? t("dialogTitleOrg")
      : target?.scopeType === "department"
        ? t("dialogTitleDept")
        : t("dialogTitleUser");

  return (
    <Modal
      open={target !== null}
      onClose={() => {
        if (!mutation.isPending) onClose();
      }}
      title={dialogTitle}
      description={t("dialogSubtitle")}
      size="sm"
      closeLabel={t("cancel")}
    >
      {target && (
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div>
            <p className="text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
              {t("targetLabel")}
            </p>
            <p className="mt-0.5 text-sm font-semibold text-[var(--text-primary)]">
              {target.name}
            </p>
          </div>

          <div>
            <p className="mb-1.5 block text-sm font-semibold text-[var(--text-primary)]">
              {t("modeLabel")}
            </p>
            <SegmentedControl
              value={mode}
              onValueChange={(v) => {
                setMode(v as "explicit" | "inherit");
                setUnitsError(null);
              }}
              ariaLabel={t("modeLabel")}
              options={[
                { value: "explicit", label: t("modeExplicit") },
                { value: "inherit", label: t("modeInherit") },
              ]}
            />
          </div>

          {mode === "explicit" && (
            <Input
              id="ceiling-units"
              type="number"
              inputMode="numeric"
              min={0}
              max={1_000_000}
              step={1}
              label={t("unitsLabel")}
              value={units}
              onChange={(e) => {
                setUnits(e.target.value);
                setUnitsError(null);
              }}
              error={unitsError ?? undefined}
              help={unitsError ? undefined : t("unitsHelp")}
              placeholder={t("unitsPlaceholder")}
              required
            />
          )}

          {formError && (
            <p role="alert" className="text-sm font-medium text-[var(--brand-red)]">
              {formError}
            </p>
          )}

          <div className="flex items-center justify-end gap-3 pt-1">
            <Button
              type="button"
              variant="ghost"
              onClick={onClose}
              disabled={mutation.isPending}
            >
              {t("cancel")}
            </Button>
            <Button type="submit" variant="primary" loading={mutation.isPending}>
              {t("save")}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}

/* -------------------------------------------------------------------------- */
/* Ceiling label                                                               */
/* -------------------------------------------------------------------------- */

function CeilingLabel({
  ceiling,
  locale,
}: {
  ceiling: number | null;
  locale: string;
}) {
  const t = useTranslations("adminConsole.aiDistribution.ceiling");
  if (ceiling == null) {
    return (
      <span className="inline-flex items-center rounded-full border border-[var(--border-default)] bg-[var(--bg-muted)] px-2 py-0.5 text-[0.6875rem] font-medium text-[var(--text-muted)]">
        {t("inherited")}
      </span>
    );
  }
  return (
    <span className="text-sm font-semibold tabular-nums text-[var(--text-primary)]">
      {t("explicit", { units: formatCredits(ceiling, locale) })}
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* Org pool card                                                               */
/* -------------------------------------------------------------------------- */

function OrgPoolCard({
  data,
  locale,
  onSetCeiling,
}: {
  data: AiAllocations;
  locale: string;
  onSetCeiling: (target: CeilingTarget) => void;
}) {
  const t = useTranslations("adminConsole.aiDistribution.pool");
  const org = data.org;
  const pct = org.energy_pct ?? 0;
  const clamped = Math.min(100, Math.max(0, pct));
  const barTone =
    clamped <= 0
      ? "bg-[var(--red-600)]"
      : clamped < 20
        ? "bg-[var(--amber-500)]"
        : "bg-[var(--text-primary)]";

  return (
    <div className="marketplace-card rounded-[12px] p-5">
      <div className="flex items-start justify-between gap-4">
        <h2 className="flex items-center gap-2 text-sm font-bold tracking-tight text-[var(--text-primary)]">
          <span className="icon-chip-primary flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm">
            <Buildings aria-hidden weight="duotone" className="size-4" />
          </span>
          {t("title")}
        </h2>
        <Button
          variant="secondary"
          size="sm"
          onClick={() =>
            onSetCeiling({
              scopeType: "org",
              scopeId: org.scope_id,
              name: t("title"),
              currentCeiling: org.weekly_allowance_units,
            })
          }
        >
          <PencilSimple aria-hidden weight="bold" className="size-3.5" />
          {t("setCeiling")}
        </Button>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
        <Stat
          label={t("effectiveLabel")}
          value={formatCredits(org.effective_allowance_units, locale)}
          sub={
            org.wallet_units > 0
              ? t("reserveLabel", {
                  wallet: formatCredits(org.wallet_units, locale),
                })
              : undefined
          }
        />
        <Stat
          label={t("usedLabel")}
          value={formatCredits(org.units_used, locale)}
        />
        <div>
          <p className="text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("energyTitle")}
          </p>
          <p
            className={cn(
              "mt-0.5 text-lg font-bold tabular-nums",
              clamped <= 0
                ? "text-[var(--red-600)]"
                : clamped < 20
                  ? "text-[var(--amber-700)]"
                  : "text-[var(--text-primary)]",
            )}
          >
            {t("energyLabel", { pct: Math.round(clamped) })}
          </p>
          <div
            role="meter"
            aria-valuenow={Math.round(clamped)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={t("energyTitle")}
            className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-[var(--bg-muted)]"
          >
            <div
              className={cn("h-full rounded-full", barTone)}
              style={{ width: `${clamped}%` }}
            />
          </div>
        </div>
      </div>

      {org.weekly_allowance_units == null && (
        <p className="mt-3 text-xs text-[var(--text-muted)]">
          {t("defaultNote")}
        </p>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div>
      <p className="text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {label}
      </p>
      <p className="mt-0.5 text-lg font-bold tabular-nums text-[var(--text-primary)]">
        {value}
      </p>
      {sub && <p className="text-xs tabular-nums text-[var(--text-muted)]">{sub}</p>}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Distribution tab                                                            */
/* -------------------------------------------------------------------------- */

function DistributionTab({ orgId }: { orgId: string }) {
  const t = useTranslations("adminConsole.aiDistribution");
  const locale = useLocale();
  const [ceilingTarget, setCeilingTarget] = useState<CeilingTarget | null>(null);

  const query = useQuery({
    queryKey: ["ai-governance", "allocations", orgId],
    queryFn: () => aiGovernanceApi.listAllocations(orgId),
    staleTime: 30_000,
    retry: 1,
  });

  const deptColumns: Column<AiAllocationDepartmentNode>[] = useMemo(
    () => [
      {
        key: "name",
        header: t("departments.colName"),
        cell: (r) => (
          <span className="font-medium text-[var(--text-primary)]">{r.name}</span>
        ),
      },
      {
        key: "ceiling",
        header: t("departments.colCeiling"),
        cell: (r) => (
          <CeilingLabel ceiling={r.weekly_allowance_units} locale={locale} />
        ),
      },
      {
        key: "used",
        header: t("departments.colUsed"),
        align: "right",
        cell: (r) => (
          <span className="text-sm tabular-nums text-[var(--text-secondary)]">
            {formatCredits(r.units_used, locale)}
          </span>
        ),
      },
      {
        key: "energy",
        header: t("departments.colEnergy"),
        cell: (r) => (
          <EnergyCell pct={r.energy_pct} inheritedLabel={t("energy.inherited")} />
        ),
      },
      {
        key: "actions",
        header: t("departments.colAction"),
        align: "right",
        cell: (r) => (
          <SetLimitButton
            onClick={() =>
              setCeilingTarget({
                scopeType: "department",
                scopeId: r.scope_id,
                name: r.name,
                currentCeiling: r.weekly_allowance_units,
              })
            }
            explicit={r.weekly_allowance_units != null}
          />
        ),
      },
    ],
    [t, locale],
  );

  const memberColumns: Column<AiAllocationMemberNode>[] = useMemo(
    () => [
      {
        key: "member",
        header: t("members.colMember"),
        cell: (r) => (
          <div className="min-w-0">
            <p className="truncate font-medium text-[var(--text-primary)]">
              {r.name || r.email || t("members.unknownMember")}
            </p>
            {r.email && r.name && (
              <p className="truncate text-xs text-[var(--text-muted)]">{r.email}</p>
            )}
          </div>
        ),
      },
      {
        key: "dept",
        header: t("members.colDept"),
        cell: (r) => (
          <span className="text-xs text-[var(--text-secondary)]">
            {r.department_ids.length === 0
              ? t("members.noDept")
              : t("members.deptCount", { count: r.department_ids.length })}
          </span>
        ),
      },
      {
        key: "ceiling",
        header: t("members.colCeiling"),
        cell: (r) => (
          <CeilingLabel ceiling={r.weekly_allowance_units} locale={locale} />
        ),
      },
      {
        key: "used",
        header: t("members.colUsed"),
        align: "right",
        cell: (r) => (
          <span className="text-sm tabular-nums text-[var(--text-secondary)]">
            {formatCredits(r.units_used, locale)}
          </span>
        ),
      },
      {
        key: "energy",
        header: t("members.colEnergy"),
        cell: (r) => (
          <EnergyCell pct={r.energy_pct} inheritedLabel={t("energy.inherited")} />
        ),
      },
      {
        key: "actions",
        header: t("members.colAction"),
        align: "right",
        cell: (r) => (
          <SetLimitButton
            onClick={() =>
              setCeilingTarget({
                scopeType: "user",
                scopeId: r.scope_id,
                name: r.name || r.email || t("members.unknownMember"),
                currentCeiling: r.weekly_allowance_units,
              })
            }
            explicit={r.weekly_allowance_units != null}
          />
        ),
      },
    ],
    [t, locale],
  );

  if (query.isPending) {
    return (
      <div className="space-y-5">
        <Skeleton className="h-40 w-full rounded-[12px]" />
        <Skeleton className="h-64 w-full rounded-[12px]" />
      </div>
    );
  }

  if (query.isError) {
    return (
      <EmptyState
        kind="error"
        icon={WarningCircle}
        title={t("error.title")}
        description={t("error.body")}
        action={
          <Button variant="secondary" onClick={() => void query.refetch()}>
            {t("error.retry")}
          </Button>
        }
      />
    );
  }

  const data = query.data;

  return (
    <div className="space-y-5">
      <OrgPoolCard data={data} locale={locale} onSetCeiling={setCeilingTarget} />

      <div className="marketplace-card rounded-[12px] p-5">
        <SectionTitle icon={UsersThree} title={t("departments.title")} />
        <DataTable
          columns={deptColumns}
          rows={data.departments}
          getRowId={(r) => r.scope_id}
          empty={{
            kind: "empty",
            title: t("departments.emptyTitle"),
            description: t("departments.emptyBody"),
          }}
          caption={t("departments.title")}
        />
      </div>

      <div className="marketplace-card rounded-[12px] p-5">
        <SectionTitle icon={User} title={t("members.title")} />
        <DataTable
          columns={memberColumns}
          rows={data.members}
          getRowId={(r) => r.scope_id}
          empty={{
            kind: "empty",
            title: t("members.emptyTitle"),
            description: t("members.emptyBody"),
          }}
          caption={t("members.title")}
        />
      </div>

      <SetCeilingDialog
        target={ceilingTarget}
        orgId={orgId}
        onClose={() => setCeilingTarget(null)}
      />
    </div>
  );
}

function SetLimitButton({
  onClick,
  explicit,
}: {
  onClick: () => void;
  explicit: boolean;
}) {
  const t = useTranslations("adminConsole.aiDistribution.ceiling");
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/50"
    >
      <PencilSimple aria-hidden weight="bold" className="size-3.5" />
      {explicit ? t("edit") : t("setLimit")}
    </button>
  );
}

function SectionTitle({
  icon: Icon,
  title,
}: {
  icon: React.ElementType;
  title: string;
}) {
  return (
    <h2 className="mb-4 flex items-center gap-2 text-sm font-bold tracking-tight text-[var(--text-primary)]">
      <span className="icon-chip-primary flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm">
        <Icon aria-hidden weight="duotone" className="size-4" />
      </span>
      {title}
    </h2>
  );
}

/* -------------------------------------------------------------------------- */
/* Capacity-requests queue                                                     */
/* -------------------------------------------------------------------------- */

function DecideDialog({
  request,
  onClose,
}: {
  request: AiCapacityRequestQueueItem | null;
  onClose: () => void;
}) {
  const t = useTranslations("adminConsole.aiDistribution.requests");
  const locale = useLocale();
  const toast = useToast();
  const qc = useQueryClient();

  const [grant, setGrant] = useState("");
  const [note, setNote] = useState("");
  const [grantError, setGrantError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [seededId, setSeededId] = useState<string | null>(null);
  if (request && seededId !== request.id) {
    setSeededId(request.id);
    setGrant(request.requested_units != null ? String(request.requested_units) : "");
    setNote("");
    setGrantError(null);
    setFormError(null);
  } else if (!request && seededId !== null) {
    setSeededId(null);
  }

  const mutation = useMutation({
    mutationFn: (decision: "approve" | "deny") => {
      if (!request) throw new Error("no request");
      if (decision === "approve") {
        return aiGovernanceApi.decideCapacityRequest(request.id, {
          decision: "approve",
          granted_units: Math.round(Number(grant)),
          note: note.trim() || null,
        });
      }
      return aiGovernanceApi.decideCapacityRequest(request.id, {
        decision: "deny",
        note: note.trim() || null,
      });
    },
    onSuccess: (_data, decision) => {
      void qc.invalidateQueries({ queryKey: ["ai-governance", "capacity-requests"] });
      void qc.invalidateQueries({ queryKey: ["ai-governance", "allocations"] });
      toast.show({
        tone: "success",
        title: decision === "approve" ? t("approvedToast") : t("deniedToast"),
      });
      onClose();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.isConflict) {
        setFormError(t("conflictToast"));
        return;
      }
      if (e instanceof ApiError && e.isValidation) {
        setFormError(e.message || t("errorToast"));
        return;
      }
      setFormError(t("errorToast"));
    },
  });

  function handleApprove() {
    setFormError(null);
    const n = Number(grant);
    if (grant.trim() === "" || !Number.isInteger(n) || n <= 0) {
      setGrantError(t("grantRequired"));
      return;
    }
    mutation.mutate("approve");
  }

  function handleDeny() {
    setFormError(null);
    mutation.mutate("deny");
  }

  const submitted = request ? formatDateTime(request.created_at, locale) : null;

  return (
    <Modal
      open={request !== null}
      onClose={() => {
        if (!mutation.isPending) onClose();
      }}
      title={t("decideTitle")}
      size="md"
      closeLabel={t("cancel")}
    >
      {request && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label={t("requesterLabel")}>
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {request.requested_by_name ||
                  request.requested_by_email ||
                  t("unknownRequester")}
              </p>
              {request.requested_by_email && request.requested_by_name && (
                <p className="text-xs text-[var(--text-muted)]">
                  {request.requested_by_email}
                </p>
              )}
              {submitted && (
                <p className="mt-0.5 text-xs text-[var(--text-muted)]">{submitted}</p>
              )}
            </Field>
            <Field label={t("requestedLabel")}>
              <p className="text-sm font-semibold tabular-nums text-[var(--text-primary)]">
                {request.requested_units != null
                  ? t("creditsValue", {
                      units: formatCredits(request.requested_units, locale),
                    })
                  : t("requestedUnset")}
              </p>
            </Field>
          </div>

          <Field label={t("reasonLabel")}>
            <p className="whitespace-pre-wrap break-words rounded-xl bg-[var(--bg-subtle)] p-3 text-sm text-[var(--text-secondary)]">
              {request.reason}
            </p>
          </Field>

          <Input
            id="grant-units"
            type="number"
            inputMode="numeric"
            min={1}
            step={1}
            label={t("grantLabel")}
            value={grant}
            onChange={(e) => {
              setGrant(e.target.value);
              setGrantError(null);
            }}
            error={grantError ?? undefined}
            help={grantError ? undefined : t("grantHelp")}
            placeholder={t("grantPlaceholder")}
          />

          <Textarea
            id="decision-note"
            label={`${t("noteLabel")} · ${t("noteOptional")}`}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder={t("notePlaceholder")}
            rows={3}
          />

          {formError && (
            <p role="alert" className="text-sm font-medium text-[var(--brand-red)]">
              {formError}
            </p>
          )}

          <div className="flex flex-col-reverse gap-3 pt-1 sm:flex-row sm:items-center sm:justify-between">
            <Button
              type="button"
              variant="danger"
              onClick={handleDeny}
              loading={mutation.isPending}
            >
              {t("denyButton")}
            </Button>
            <Button
              type="button"
              variant="primary"
              onClick={handleApprove}
              loading={mutation.isPending}
            >
              {t("approveButton")}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="mb-1 text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {label}
      </p>
      {children}
    </div>
  );
}

function CapacityRequestsTab() {
  const t = useTranslations("adminConsole.aiDistribution.requests");
  const locale = useLocale();
  const [status, setStatus] = useState<CapacityRequestStatus>("pending");
  const [decideTarget, setDecideTarget] =
    useState<AiCapacityRequestQueueItem | null>(null);

  const query = useQuery({
    queryKey: ["ai-governance", "capacity-requests", status],
    queryFn: () => aiGovernanceApi.listCapacityRequests(status),
    staleTime: 15_000,
    retry: 1,
  });

  const statusLabel: Record<CapacityRequestStatus, string> = {
    pending: t("statusPending"),
    approved: t("statusApproved"),
    denied: t("statusDenied"),
  };

  const columns: Column<AiCapacityRequestQueueItem>[] = useMemo(
    () => [
      {
        key: "requester",
        header: t("colRequester"),
        cell: (r) => (
          <div className="min-w-0">
            <p className="truncate font-medium text-[var(--text-primary)]">
              {r.requested_by_name || r.requested_by_email || t("unknownRequester")}
            </p>
            {r.requested_by_email && r.requested_by_name && (
              <p className="truncate text-xs text-[var(--text-muted)]">
                {r.requested_by_email}
              </p>
            )}
          </div>
        ),
      },
      {
        key: "reason",
        header: t("colReason"),
        cell: (r) => (
          <span className="line-clamp-2 max-w-xs text-sm text-[var(--text-secondary)]">
            {r.reason}
          </span>
        ),
      },
      {
        key: "requested",
        header: t("colRequested"),
        align: "right",
        cell: (r) => (
          <span className="text-sm tabular-nums text-[var(--text-secondary)]">
            {r.requested_units != null
              ? t("creditsValue", {
                  units: formatCredits(r.requested_units, locale),
                })
              : t("requestedUnset")}
          </span>
        ),
      },
      {
        key: "submitted",
        header: t("colSubmitted"),
        cell: (r) => (
          <span className="text-xs text-[var(--text-muted)]">
            {formatDate(r.created_at, locale) ?? ""}
          </span>
        ),
      },
      {
        key: "actions",
        header: t("colAction"),
        align: "right",
        cell: (r) =>
          r.status === "pending" ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setDecideTarget(r)}
            >
              {t("review")}
            </Button>
          ) : (
            <StatusBadge tone={capacityStatusTone(r.status)}>
              {statusLabel[r.status]}
            </StatusBadge>
          ),
      },
    ],
    // statusLabel is derived from `t`; it maps all statuses so the columns do
    // not depend on the current filter value.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [t, locale],
  );

  return (
    <div className="marketplace-card rounded-[12px] p-5">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-sm font-bold tracking-tight text-[var(--text-primary)]">
            {t("title")}
          </h2>
          <p className="mt-0.5 max-w-prose text-xs text-[var(--text-secondary)]">
            {t("subtitle")}
          </p>
        </div>
        <SegmentedControl
          value={status}
          onValueChange={(v) => setStatus(v as CapacityRequestStatus)}
          ariaLabel={t("filterLabel")}
          size="sm"
          options={[
            { value: "pending", label: t("statusPending") },
            { value: "approved", label: t("statusApproved") },
            { value: "denied", label: t("statusDenied") },
          ]}
        />
      </div>

      {query.isError ? (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("errorTitle")}
          description={t("errorBody")}
          action={
            <Button variant="secondary" onClick={() => void query.refetch()}>
              {t("retry")}
            </Button>
          }
        />
      ) : (
        <DataTable
          columns={columns}
          rows={query.data ?? []}
          getRowId={(r) => r.id}
          loading={query.isPending}
          empty={{
            kind: "empty",
            title: t("emptyTitle"),
            description: t("emptyBody", { status: statusLabel[status].toLowerCase() }),
          }}
          caption={t("title")}
        />
      )}

      <DecideDialog request={decideTarget} onClose={() => setDecideTarget(null)} />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Screen                                                                      */
/* -------------------------------------------------------------------------- */

export function AiAllocationsScreen() {
  const t = useTranslations("adminConsole.aiDistribution");
  const orgId = useAuthStore((s) => s.user?.orgId ?? null);
  const tabsId = useId();
  const [tab, setTab] = useState<"distribution" | "requests">("distribution");

  const tabItems: TabItem[] = [
    { value: "distribution", label: t("tabs.distribution") },
    { value: "requests", label: t("tabs.requests") },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold tracking-tight text-[var(--text-primary)]">
          {t("pageTitle")}
        </h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          {t("pageSubtitle")}
        </p>
        <p className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-[var(--bg-subtle)] px-2.5 py-1 text-xs text-[var(--text-muted)]">
          <ShieldWarning aria-hidden weight="duotone" className="size-3.5" />
          {t("masked")}
        </p>
      </div>

      {orgId == null ? (
        <EmptyState
          kind="permission"
          icon={Lightning}
          title={t("noOrg.title")}
          description={t("noOrg.body")}
        />
      ) : (
        <>
          <Tabs
            idBase={tabsId}
            items={tabItems}
            value={tab}
            onValueChange={(v) => setTab(v as "distribution" | "requests")}
            ariaLabel={t("pageTitle")}
          />
          <TabPanel tabsId={tabsId} value="distribution" active={tab === "distribution"}>
            <DistributionTab orgId={orgId} />
          </TabPanel>
          <TabPanel tabsId={tabsId} value="requests" active={tab === "requests"}>
            <CapacityRequestsTab />
          </TabPanel>
        </>
      )}
    </div>
  );
}
