"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Lightning,
  TreeStructure,
  User,
  Wallet,
  Receipt,
  CheckCircle,
  PencilSimple,
  X,
  ShieldWarning,
  SignIn,
  WarningCircle,
  Info,
} from "@phosphor-icons/react";
import {
  Button,
  EmptyState,
  Input,
  Modal,
  Skeleton,
  StatusBadge,
  Textarea,
  useToast,
} from "@/components/ui";
import {
  ApiError,
  aiEnergyApi,
  organizationApi,
  type AiEnergyAllocation,
  type AiEnergyOverview,
  type AiEnergyTopup,
  type OrgEnergyPool,
} from "@/lib/api";
import {
  clampPct,
  energyTone,
  formatUnits,
  TOPUP_STATUS_TONE,
} from "@/lib/ai-energy/format";
import { formatVnd, formatDate } from "@/lib/billing/format";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { useAuthStore } from "@/stores/auth-store";
import { cn } from "@/lib/utils";

/**
 * Partner-admin AI energy governance (org tab). Renders the shared org energy
 * pool meter, a table of department + member sub-allocations with an inline
 * weekly-cap editor and a goodwill wallet grant, and the org's bank-transfer
 * top-ups. Confirming a top-up is finance authority (VinUni) — a partner admin
 * sees the list but a disabled, explained confirm control.
 *
 * Energy is an opaque product credit: no tokens/USD/provider/model appear. A
 * top-up's VND `price_amount` is a real product price and is shown.
 */
export function AiEnergyTab() {
  const t = useTranslations("aiEnergy");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const isSuperadmin = useAuthStore((s) => s.user?.isSuperadmin ?? false);

  const overview = useQuery({
    queryKey: ["org", "ai-energy", "overview"],
    queryFn: () => aiEnergyApi.getOverview(),
    retry: false,
  });
  const membersQuery = useQuery({
    queryKey: ["org", "members"],
    queryFn: () => organizationApi.listMembers(),
    retry: false,
  });
  const departmentsQuery = useQuery({
    queryKey: ["org", "departments"],
    queryFn: () => organizationApi.listDepartments(),
    retry: false,
  });
  const topupsQuery = useQuery({
    queryKey: ["org", "ai-energy", "topups"],
    queryFn: () => aiEnergyApi.listOrgTopups(),
    retry: false,
  });

  /* ---- Permission / auth gate on the management-only overview ---- */
  if (overview.isError && overview.error instanceof ApiError) {
    const err = overview.error;
    if (err.isPermissionError) {
      return (
        <EmptyState
          kind="permission"
          icon={ShieldWarning}
          title={tStates("permissionTitle")}
          description={t("admin.permissionBody")}
        />
      );
    }
    if (err.isAuthError) {
      return (
        <EmptyState
          kind="auth"
          icon={SignIn}
          title={tStates("authTitle")}
          description={tStates("authBody")}
        />
      );
    }
    return (
      <EmptyState
        kind="error"
        icon={WarningCircle}
        title={tStates("errorTitle")}
        description={tStates("errorBody")}
        action={
          <Button variant="secondary" onClick={() => overview.refetch()}>
            {tc("retry")}
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      <p className="max-w-2xl text-sm text-[var(--text-secondary)]">
        {t("admin.intro")}
      </p>

      {overview.isPending || !overview.data ? (
        <LoadingState />
      ) : (
        <OverviewBody
          data={overview.data}
          members={membersQuery.data?.data ?? []}
          departments={departmentsQuery.data ?? []}
          topups={topupsQuery.data ?? []}
          topupsLoading={topupsQuery.isPending}
          topupsError={topupsQuery.isError}
          canFinance={isSuperadmin}
          locale={locale}
        />
      )}
    </div>
  );
}

function LoadingState() {
  return (
    <div className="space-y-6">
      <div className="space-y-3 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-2 w-full" />
        <Skeleton className="h-4 w-32" />
      </div>
      <div className="space-y-2 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Body                                                                        */
/* -------------------------------------------------------------------------- */

type MemberLite = { user_id?: string | null; user_email: string; full_name?: string | null };
type DepartmentLite = { id: string; name: string };

interface AllocRow {
  key: string;
  scopeType: "department" | "user";
  scopeId: string;
  name: string;
  subtitle?: string | null;
  allocation: AiEnergyAllocation | null;
}

function OverviewBody({
  data,
  members,
  departments,
  topups,
  topupsLoading,
  topupsError,
  canFinance,
  locale,
}: {
  data: AiEnergyOverview;
  members: MemberLite[];
  departments: DepartmentLite[];
  topups: AiEnergyTopup[];
  topupsLoading: boolean;
  topupsError: boolean;
  canFinance: boolean;
  locale: string;
}) {
  const t = useTranslations("aiEnergy");
  const qc = useQueryClient();
  const toast = useToast();
  const getMessage = useApiErrorMessage();

  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [capDraft, setCapDraft] = useState("");
  const [grantTarget, setGrantTarget] = useState<AllocRow | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<AiEnergyTopup | null>(null);

  const allocByScope = useMemo(() => {
    const map = new Map<string, AiEnergyAllocation>();
    for (const a of data.allocations) map.set(a.scope_id, a);
    return map;
  }, [data.allocations]);

  const rows = useMemo<AllocRow[]>(() => {
    const deptRows: AllocRow[] = departments.map((d) => ({
      key: `dept-${d.id}`,
      scopeType: "department",
      scopeId: d.id,
      name: d.name,
      allocation: allocByScope.get(d.id) ?? null,
    }));
    const memberRows: AllocRow[] = members
      .filter((m) => Boolean(m.user_id))
      .map((m) => ({
        key: `user-${m.user_id}`,
        scopeType: "user",
        scopeId: m.user_id as string,
        name: m.full_name?.trim() || m.user_email,
        subtitle: m.full_name?.trim() ? m.user_email : null,
        allocation: allocByScope.get(m.user_id as string) ?? null,
      }));
    return [...deptRows, ...memberRows];
  }, [departments, members, allocByScope]);

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["org", "ai-energy"] });
    // The sidebar/billing energy meters reflect the shared pool — refresh them.
    void qc.invalidateQueries({ queryKey: ["ai", "usage"] });
  }

  const allocation = useMutation({
    mutationFn: (vars: {
      scope_type: "department" | "user";
      scope_id: string;
      weekly_allowance_units: number | null;
    }) => aiEnergyApi.setAllocation(vars),
    onSuccess: (_res, vars) => {
      setEditingKey(null);
      toast.show({
        tone: "success",
        title:
          vars.weekly_allowance_units == null
            ? t("admin.toast.allocationCleared")
            : t("admin.toast.allocationSaved"),
      });
      refresh();
    },
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  const grant = useMutation({
    mutationFn: (vars: {
      scope_type: "department" | "user";
      scope_id: string;
      units: number;
      reason: string;
    }) => aiEnergyApi.grantWallet(vars),
    onSuccess: () => {
      setGrantTarget(null);
      toast.show({ tone: "success", title: t("admin.toast.walletGranted") });
      refresh();
    },
    onError: (e) => {
      setGrantTarget(null);
      toast.show({ tone: "error", title: getMessage(e) });
    },
  });

  const confirmTopup = useMutation({
    mutationFn: (vars: { id: string; reference: string }) =>
      aiEnergyApi.confirmTopup(vars.id, vars.reference),
    onSuccess: () => {
      setConfirmTarget(null);
      toast.show({ tone: "success", title: t("admin.toast.topupConfirmed") });
      refresh();
    },
    onError: (e) => {
      setConfirmTarget(null);
      if (e instanceof ApiError && e.isPermissionError) {
        toast.show({ tone: "error", title: t("admin.topups.confirmDisabled") });
        return;
      }
      toast.show({ tone: "error", title: getMessage(e) });
    },
  });

  function startEdit(row: AllocRow) {
    setEditingKey(row.key);
    setCapDraft(
      row.allocation?.weekly_allowance_units != null
        ? String(row.allocation.weekly_allowance_units)
        : "",
    );
  }

  function saveCap(row: AllocRow) {
    const trimmed = capDraft.trim();
    const value = trimmed === "" ? null : Number(trimmed);
    if (value != null && (Number.isNaN(value) || value < 0)) return;
    allocation.mutate({
      scope_type: row.scopeType,
      scope_id: row.scopeId,
      weekly_allowance_units: value,
    });
  }

  return (
    <div className="space-y-6">
      <PoolMeter pool={data.org_pool} locale={locale} />

      <PacksReference packs={data.packs} locale={locale} />

      {/* Allocations */}
      <section aria-label={t("admin.allocations.title")}>
        <SectionHeading
          icon={TreeStructure}
          title={t("admin.allocations.title")}
          hint={t("admin.allocations.intro")}
        />
        {rows.length === 0 ? (
          <EmptyState
            kind="empty"
            icon={User}
            title={t("admin.allocations.emptyTitle")}
            description={t("admin.allocations.emptyBody")}
          />
        ) : (
          <div className="overflow-x-auto rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)]">
            <table className="w-full border-collapse text-sm">
              <caption className="sr-only">
                {t("admin.allocations.title")}
              </caption>
              <thead>
                <tr className="border-b border-[var(--border-default)] bg-[var(--bg-subtle)] text-left">
                  <Th>{t("admin.allocations.scopeCol")}</Th>
                  <Th>{t("admin.allocations.capCol")}</Th>
                  <Th align="right">{t("admin.allocations.walletCol")}</Th>
                  <Th align="right">{t("admin.allocations.usedCol")}</Th>
                  <Th align="right">{t("admin.allocations.actionsCol")}</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const isEditing = editingKey === row.key;
                  const cap = row.allocation?.weekly_allowance_units ?? null;
                  const wallet = row.allocation?.wallet_units ?? 0;
                  const used = row.allocation?.weekly_used ?? 0;
                  const busy =
                    allocation.isPending &&
                    allocation.variables?.scope_id === row.scopeId;
                  const ScopeIcon =
                    row.scopeType === "department" ? TreeStructure : User;
                  return (
                    <tr
                      key={row.key}
                      className="border-b border-[var(--border-default)] align-middle last:border-0"
                    >
                      {/* Scope */}
                      <td className="px-3.5 py-2.5">
                        <div className="flex items-center gap-2.5">
                          <span className="flex size-7 shrink-0 items-center justify-center rounded-lg border border-[var(--border-default)] bg-[var(--bg-subtle)] text-[var(--text-secondary)]">
                            <ScopeIcon
                              aria-hidden
                              weight="duotone"
                              className="size-4"
                            />
                          </span>
                          <div className="min-w-0">
                            <p className="truncate font-semibold text-[var(--text-primary)]">
                              {row.name}
                            </p>
                            <p className="truncate text-xs text-[var(--text-muted)]">
                              {row.subtitle ??
                                t(
                                  row.scopeType === "department"
                                    ? "scope.department"
                                    : "scope.user",
                                )}
                            </p>
                          </div>
                        </div>
                      </td>

                      {/* Weekly cap */}
                      <td className="px-3.5 py-2.5">
                        {isEditing ? (
                          <div className="flex items-center gap-1.5">
                            <div className="w-24">
                              <Input
                                type="number"
                                min={0}
                                inputMode="numeric"
                                value={capDraft}
                                onChange={(e) => setCapDraft(e.target.value)}
                                placeholder={t("admin.allocations.shared")}
                                aria-label={t("admin.allocations.capLabel")}
                                disabled={busy}
                              />
                            </div>
                            <Button
                              size="sm"
                              onClick={() => saveCap(row)}
                              loading={busy}
                            >
                              {t("admin.allocations.save")}
                            </Button>
                            <button
                              type="button"
                              onClick={() => setEditingKey(null)}
                              aria-label={t("admin.allocations.cancel")}
                              className="rounded-lg p-1.5 text-[var(--text-muted)] outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
                            >
                              <X aria-hidden weight="bold" className="size-4" />
                            </button>
                          </div>
                        ) : (
                          <div className="flex items-center gap-2">
                            <span
                              className={cn(
                                "font-medium tabular-nums",
                                cap != null
                                  ? "text-[var(--text-primary)]"
                                  : "text-[var(--text-muted)]",
                              )}
                            >
                              {cap != null
                                ? t("admin.allocations.perWeek", {
                                    units: formatUnits(cap, locale),
                                  })
                                : t("admin.allocations.shared")}
                            </span>
                            <button
                              type="button"
                              onClick={() => startEdit(row)}
                              aria-label={t("admin.allocations.editCap", {
                                name: row.name,
                              })}
                              className="rounded-lg p-1 text-[var(--text-muted)] outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
                            >
                              <PencilSimple
                                aria-hidden
                                weight="bold"
                                className="size-3.5"
                              />
                            </button>
                          </div>
                        )}
                      </td>

                      {/* Wallet reserve */}
                      <td className="px-3.5 py-2.5 text-right tabular-nums text-[var(--text-secondary)]">
                        {wallet > 0
                          ? t("admin.allocations.reserve", {
                              units: formatUnits(wallet, locale),
                            })
                          : "—"}
                      </td>

                      {/* Weekly used */}
                      <td className="px-3.5 py-2.5 text-right tabular-nums text-[var(--text-secondary)]">
                        {row.scopeType === "user" ? (
                          formatUnits(used, locale)
                        ) : (
                          <span
                            className="text-[var(--text-muted)]"
                            title={t("admin.allocations.advisory")}
                          >
                            —
                          </span>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="px-3.5 py-2.5 text-right">
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => setGrantTarget(row)}
                        >
                          <Wallet
                            aria-hidden
                            weight="duotone"
                            className="size-3.5"
                          />
                          {t("admin.allocations.grantWallet")}
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Top-ups */}
      <TopupsSection
        topups={topups}
        loading={topupsLoading}
        error={topupsError}
        canFinance={canFinance}
        locale={locale}
        onConfirm={setConfirmTarget}
        rowsForName={rows}
      />

      {/* Grant wallet modal */}
      {grantTarget && (
        <GrantWalletModal
          target={grantTarget}
          pending={grant.isPending}
          onClose={() => setGrantTarget(null)}
          onSubmit={(units, reason) =>
            grant.mutate({
              scope_type: grantTarget.scopeType,
              scope_id: grantTarget.scopeId,
              units,
              reason,
            })
          }
        />
      )}

      {/* Confirm top-up modal (finance only) */}
      {confirmTarget && (
        <ConfirmTopupModal
          topup={confirmTarget}
          pending={confirmTopup.isPending}
          locale={locale}
          onClose={() => setConfirmTarget(null)}
          onSubmit={(reference) =>
            confirmTopup.mutate({ id: confirmTarget.id, reference })
          }
        />
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Pool meter                                                                  */
/* -------------------------------------------------------------------------- */

function PoolMeter({ pool, locale }: { pool: OrgEnergyPool; locale: string }) {
  const t = useTranslations("aiEnergy");
  const tone = energyTone(pool);
  const pct = Math.round(clampPct(pool.energy_pct));

  return (
    <section
      aria-label={t("admin.poolTitle")}
      className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4 shadow-[0_2px_16px_rgba(11,34,57,0.06)]"
    >
      <div className="mb-3 flex items-center gap-2">
        <span className="flex size-7 items-center justify-center rounded-lg icon-chip-primary shadow-sm">
          <Lightning aria-hidden weight="duotone" className="size-4 text-white" />
        </span>
        <h3 className="text-sm font-bold text-[var(--text-primary)]">
          {t("admin.poolTitle")}
        </h3>
      </div>

      <div className="flex items-end justify-between gap-3">
        <p
          className={cn(
            "text-2xl font-bold tabular-nums leading-tight",
            tone === "critical"
              ? "text-[var(--red-600)]"
              : "text-[var(--text-primary)]",
          )}
        >
          {t("admin.remaining", { pct })}
        </p>
        <div className="shrink-0 text-right">
          <p className="text-sm font-semibold tabular-nums text-[var(--text-primary)]">
            {t("admin.weeklyLabel", {
              used: formatUnits(pool.weekly.used, locale),
              allowance: formatUnits(pool.weekly.allowance, locale),
            })}
          </p>
          {pool.weekly.wallet > 0 && (
            <p className="text-xs tabular-nums text-[var(--text-muted)]">
              {t("admin.walletLabel", {
                wallet: formatUnits(pool.weekly.wallet, locale),
              })}
            </p>
          )}
        </div>
      </div>

      <div
        role="meter"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={t("admin.poolTitle")}
        className="mt-2 h-2 w-full overflow-hidden rounded-full bg-[var(--bg-muted)]"
      >
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-500 motion-reduce:transition-none",
            tone === "critical"
              ? "bg-[var(--red-600)]"
              : tone === "warning"
                ? "bg-[var(--amber-500)]"
                : "bg-[var(--text-primary)]",
          )}
          style={{ width: `${clampPct(pool.energy_pct)}%` }}
        />
      </div>

      {pool.blocked ? (
        <Banner tone="error">{t("admin.blockedPool")}</Banner>
      ) : pool.warning ? (
        <Banner tone="warning">{t("admin.warningPool")}</Banner>
      ) : null}
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/* Packs reference                                                             */
/* -------------------------------------------------------------------------- */

function PacksReference({
  packs,
  locale,
}: {
  packs: AiEnergyOverview["packs"];
  locale: string;
}) {
  const t = useTranslations("aiEnergy");
  if (packs.length === 0) return null;
  return (
    <section aria-label={t("admin.packsTitle")}>
      <SectionHeading icon={Receipt} title={t("admin.packsTitle")} />
      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        {packs.map((p) => (
          <li
            key={p.code}
            className="flex items-baseline justify-between gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-3.5 py-2.5"
          >
            <span className="text-sm font-semibold text-[var(--text-primary)]">
              {t("admin.packLabel", { units: formatUnits(p.units, locale) })}
            </span>
            <span className="text-sm tabular-nums text-[var(--text-secondary)]">
              {formatVnd(p.price_amount, p.currency, locale)}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/* Top-ups                                                                     */
/* -------------------------------------------------------------------------- */

function TopupsSection({
  topups,
  loading,
  error,
  canFinance,
  locale,
  onConfirm,
  rowsForName,
}: {
  topups: AiEnergyTopup[];
  loading: boolean;
  error: boolean;
  canFinance: boolean;
  locale: string;
  onConfirm: (t: AiEnergyTopup) => void;
  rowsForName: AllocRow[];
}) {
  const t = useTranslations("aiEnergy");
  const tStates = useTranslations("states");

  const nameFor = (scopeId: string, scopeType: string): string => {
    const row = rowsForName.find((r) => r.scopeId === scopeId);
    if (row) return row.name;
    if (scopeType === "org") return t("scope.org");
    return t(scopeType === "department" ? "scope.department" : "scope.user");
  };

  return (
    <section aria-label={t("admin.topups.title")}>
      <SectionHeading
        icon={Receipt}
        title={t("admin.topups.title")}
        hint={t("admin.topups.intro")}
      />

      {!canFinance && (
        <div className="mb-3 flex items-start gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--bg-subtle)] px-3.5 py-2.5 text-sm text-[var(--text-secondary)]">
          <Info
            aria-hidden
            weight="duotone"
            className="mt-0.5 size-4 shrink-0 text-[var(--text-muted)]"
          />
          <span>{t("admin.topups.financeNote")}</span>
        </div>
      )}

      {loading ? (
        <div className="space-y-2 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4">
          <Skeleton className="h-6 w-full" />
          <Skeleton className="h-6 w-full" />
        </div>
      ) : error ? (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={tStates("errorTitle")}
          description={tStates("errorBody")}
        />
      ) : topups.length === 0 ? (
        <EmptyState
          kind="empty"
          icon={Receipt}
          title={t("admin.topups.emptyTitle")}
          description={t("admin.topups.emptyBody")}
        />
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)]">
          <table className="w-full border-collapse text-sm">
            <caption className="sr-only">{t("admin.topups.title")}</caption>
            <thead>
              <tr className="border-b border-[var(--border-default)] bg-[var(--bg-subtle)] text-left">
                <Th>{t("admin.topups.dateCol")}</Th>
                <Th>{t("admin.topups.scopeCol")}</Th>
                <Th align="right">{t("admin.topups.unitsCol")}</Th>
                <Th align="right">{t("admin.topups.priceCol")}</Th>
                <Th>{t("admin.topups.statusCol")}</Th>
                <Th align="right">{t("admin.topups.actionCol")}</Th>
              </tr>
            </thead>
            <tbody>
              {topups.map((row) => (
                <tr
                  key={row.id}
                  className="border-b border-[var(--border-default)] align-middle last:border-0"
                >
                  <td className="px-3.5 py-2.5 tabular-nums text-[var(--text-secondary)]">
                    {formatDate(row.created_at, locale)}
                  </td>
                  <td className="px-3.5 py-2.5 text-[var(--text-primary)]">
                    {nameFor(row.scope_id, row.scope_type)}
                  </td>
                  <td className="px-3.5 py-2.5 text-right tabular-nums text-[var(--text-primary)]">
                    {formatUnits(row.units, locale)}
                  </td>
                  <td className="px-3.5 py-2.5 text-right tabular-nums font-semibold text-[var(--text-primary)]">
                    {formatVnd(row.price_amount, row.currency, locale)}
                  </td>
                  <td className="px-3.5 py-2.5">
                    <StatusBadge tone={TOPUP_STATUS_TONE[row.status]}>
                      {row.status_label}
                    </StatusBadge>
                  </td>
                  <td className="px-3.5 py-2.5 text-right">
                    {row.status === "pending" ? (
                      canFinance ? (
                        <Button
                          size="sm"
                          onClick={() => onConfirm(row)}
                        >
                          <CheckCircle
                            aria-hidden
                            weight="duotone"
                            className="size-3.5"
                          />
                          {t("admin.topups.confirm")}
                        </Button>
                      ) : (
                        <span
                          className="inline-flex cursor-not-allowed items-center gap-1.5 rounded-full border border-[var(--border-default)] px-2.5 py-1 text-xs font-medium text-[var(--text-muted)]"
                          title={t("admin.topups.confirmDisabled")}
                        >
                          {t("admin.topups.awaitingFinance")}
                        </span>
                      )
                    ) : (
                      <span className="text-[var(--text-muted)]">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/* Modals                                                                      */
/* -------------------------------------------------------------------------- */

function GrantWalletModal({
  target,
  pending,
  onClose,
  onSubmit,
}: {
  target: AllocRow;
  pending: boolean;
  onClose: () => void;
  onSubmit: (units: number, reason: string) => void;
}) {
  const t = useTranslations("aiEnergy");
  const tc = useTranslations("common");
  const [units, setUnits] = useState("");
  const [reason, setReason] = useState("");

  const unitsValue = Number(units.trim());
  const valid =
    units.trim() !== "" &&
    !Number.isNaN(unitsValue) &&
    unitsValue >= 1 &&
    reason.trim().length > 0;

  return (
    <Modal
      open
      onClose={onClose}
      title={t("admin.grant.title")}
      description={t("admin.grant.body", { name: target.name })}
      size="sm"
      closeLabel={tc("close")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            {tc("cancel")}
          </Button>
          <Button
            onClick={() => onSubmit(unitsValue, reason.trim())}
            disabled={!valid}
            loading={pending}
          >
            {t("admin.grant.submit")}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input
          type="number"
          min={1}
          inputMode="numeric"
          label={t("admin.grant.unitsLabel")}
          required
          value={units}
          onChange={(e) => setUnits(e.target.value)}
          placeholder="200"
        />
        <Textarea
          label={t("admin.grant.reasonLabel")}
          required
          rows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder={t("admin.grant.reasonPlaceholder")}
          maxLength={200}
        />
      </div>
    </Modal>
  );
}

function ConfirmTopupModal({
  topup,
  pending,
  locale,
  onClose,
  onSubmit,
}: {
  topup: AiEnergyTopup;
  pending: boolean;
  locale: string;
  onClose: () => void;
  onSubmit: (reference: string) => void;
}) {
  const t = useTranslations("aiEnergy");
  const tc = useTranslations("common");
  const [reference, setReference] = useState(topup.payment_reference ?? "");
  const valid = reference.trim().length > 0;

  return (
    <Modal
      open
      onClose={onClose}
      title={t("admin.topups.confirmTitle")}
      description={t("admin.topups.confirmBody", {
        units: formatUnits(topup.units, locale),
        price: formatVnd(topup.price_amount, topup.currency, locale),
      })}
      size="sm"
      closeLabel={tc("close")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            {tc("cancel")}
          </Button>
          <Button
            onClick={() => onSubmit(reference.trim())}
            disabled={!valid}
            loading={pending}
          >
            {t("admin.topups.confirmAction")}
          </Button>
        </>
      }
    >
      <Input
        label={t("admin.topups.referenceLabel")}
        required
        value={reference}
        onChange={(e) => setReference(e.target.value)}
        placeholder={t("admin.topups.referencePlaceholder")}
        maxLength={120}
      />
    </Modal>
  );
}

/* -------------------------------------------------------------------------- */
/* Small shared bits                                                           */
/* -------------------------------------------------------------------------- */

function SectionHeading({
  icon: Icon,
  title,
  hint,
}: {
  icon: React.ElementType;
  title: string;
  hint?: string;
}) {
  return (
    <div className="mb-2.5">
      <h3 className="flex items-center gap-1.5 text-sm font-bold text-[var(--text-primary)]">
        <Icon aria-hidden weight="duotone" className="size-4 text-[var(--text-muted)]" />
        {title}
      </h3>
      {hint && (
        <p className="mt-0.5 text-xs text-[var(--text-secondary)]">{hint}</p>
      )}
    </div>
  );
}

function Th({
  children,
  align = "left",
}: {
  children: React.ReactNode;
  align?: "left" | "right";
}) {
  return (
    <th
      scope="col"
      className={cn(
        "px-3.5 py-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]",
        align === "right" ? "text-right" : "text-left",
      )}
    >
      {children}
    </th>
  );
}

function Banner({
  tone,
  children,
}: {
  tone: "warning" | "error";
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "mt-3 rounded-lg border px-3.5 py-2.5 text-sm font-medium",
        tone === "error"
          ? "border-[var(--red-400)] bg-[var(--red-50)] text-[var(--red-700)]"
          : "border-[var(--amber-400)] bg-[var(--amber-50)] text-[var(--amber-700)]",
      )}
    >
      {children}
    </div>
  );
}
