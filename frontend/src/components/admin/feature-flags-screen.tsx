"use client";

import { useId, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ToggleRight,
  Plus,
  PencilSimple,
  Warning,
  WarningCircle,
  ShieldCheck,
} from "@phosphor-icons/react";
import {
  DataTable,
  Sheet,
  EmptyState,
  Skeleton,
  Button,
  Input,
  Switch,
  Tabs,
  TabPanel,
  useToast,
  type Column,
  type TabItem,
} from "@/components/ui";
import {
  featureFlagsApi,
  type FeatureFlag,
  type FeatureFlagCreateBody,
  type FeatureFlagUpdateBody,
  type PermissionCatalogEntry,
} from "@/lib/api/feature-flags";
import { ApiError } from "@/lib/api";

/* -------------------------------------------------------------------------- */
/* Helpers                                                                     */
/* -------------------------------------------------------------------------- */

const FLAG_KEY_RE = /^[a-z0-9][a-z0-9._-]*[a-z0-9]$|^[a-z0-9]$/;

function isValidKey(s: string): boolean {
  return FLAG_KEY_RE.test(s.trim());
}

function isValidRollout(s: string): boolean {
  const n = parseInt(s, 10);
  return !isNaN(n) && n >= 0 && n <= 100 && String(n) === s.trim();
}

/* -------------------------------------------------------------------------- */
/* Rollout bar                                                                 */
/* -------------------------------------------------------------------------- */

function RolloutBar({ pct, enabled }: { pct: number; enabled: boolean }) {
  const capped = Math.min(100, Math.max(0, pct));
  return (
    <div className="flex items-center gap-2">
      <div
        className="h-1.5 w-20 overflow-hidden rounded-full bg-[var(--gray-200)]"
        aria-hidden
      >
        <div
          className={
            enabled && capped > 0
              ? "h-full rounded-full bg-[var(--brand-primary)] transition-all"
              : "h-full rounded-full bg-[var(--gray-300)] transition-all"
          }
          style={{ width: `${capped}%` }}
        />
      </div>
      <span className="tabular-nums text-xs text-[var(--text-secondary)]">
        {capped}%
      </span>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Flag form state types                                                       */
/* -------------------------------------------------------------------------- */

interface FlagFormState {
  key: string;
  description: string;
  enabled: boolean;
  rollout_percentage: string;
}

interface FlagFormErrors {
  key?: string;
  description?: string;
  rollout_percentage?: string;
  conflict?: string;
}

const EMPTY_FORM: FlagFormState = {
  key: "",
  description: "",
  enabled: true,
  rollout_percentage: "100",
};

function flagToForm(f: FeatureFlag): FlagFormState {
  return {
    key: f.key,
    description: f.description,
    enabled: f.enabled,
    rollout_percentage: String(f.rollout_percentage),
  };
}

/* -------------------------------------------------------------------------- */
/* Flag form sheet                                                             */
/* -------------------------------------------------------------------------- */

function FlagFormSheet({
  open,
  editing,
  onClose,
}: {
  open: boolean;
  editing: FeatureFlag | null;
  onClose: () => void;
}) {
  const t = useTranslations("adminConsole.featureFlags.flags");
  const tRoot = useTranslations("adminConsole.featureFlags");
  const toast = useToast();
  const qc = useQueryClient();

  const [form, setForm] = useState<FlagFormState>(
    editing ? flagToForm(editing) : EMPTY_FORM,
  );
  const [errors, setErrors] = useState<FlagFormErrors>({});

  function patch(partial: Partial<FlagFormState>) {
    setForm((f) => ({ ...f, ...partial }));
    setErrors((e) => {
      const next = { ...e };
      for (const k of Object.keys(partial) as (keyof FlagFormState)[]) {
        delete (next as Record<string, string | undefined>)[k];
      }
      delete next.conflict;
      return next;
    });
  }

  function validate(): FlagFormErrors {
    const errs: FlagFormErrors = {};
    if (!editing) {
      if (!form.key.trim()) {
        errs.key = t("sheet.validationKeyRequired");
      } else if (!isValidKey(form.key)) {
        errs.key = t("sheet.validationKey");
      }
    }
    if (!isValidRollout(form.rollout_percentage)) {
      errs.rollout_percentage = t("sheet.validationRollout");
    }
    return errs;
  }

  const createMutation = useMutation({
    mutationFn: (body: FeatureFlagCreateBody) => featureFlagsApi.create(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["feature-flags"] });
      toast.show({ tone: "success", title: t("sheet.save") });
      onClose();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.isConflict) {
        setErrors((prev) => ({ ...prev, conflict: t("sheet.conflictError") }));
        return;
      }
      if (e instanceof ApiError && e.isValidation) {
        const msg = typeof e.message === "string" && e.message
          ? e.message
          : t("sheet.validationBackend");
        setErrors((prev) => ({ ...prev, key: msg }));
        return;
      }
      toast.show({ tone: "error", title: tRoot("retry") });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: FeatureFlagUpdateBody }) =>
      featureFlagsApi.update(id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["feature-flags"] });
      toast.show({ tone: "success", title: t("sheet.save") });
      onClose();
    },
    onError: () => {
      toast.show({ tone: "error", title: tRoot("retry") });
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

    const rollout = parseInt(form.rollout_percentage, 10);

    if (editing) {
      const body: FeatureFlagUpdateBody = {
        enabled: form.enabled,
        description: form.description.trim() || undefined,
        rollout_percentage: rollout,
      };
      updateMutation.mutate({ id: editing.id, body });
    } else {
      const body: FeatureFlagCreateBody = {
        key: form.key.trim(),
        description: form.description.trim(),
        enabled: form.enabled,
        rollout_percentage: rollout,
      };
      createMutation.mutate(body);
    }
  }

  return (
    <Sheet
      open={open}
      onClose={() => {
        if (!isPending) onClose();
      }}
      title={editing ? t("sheet.editTitle") : t("sheet.addTitle")}
      closeLabel={t("sheet.cancel")}
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {/* Key — read-only when editing */}
        {editing ? (
          <div>
            <span className="mb-1 block text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
              {t("sheet.labelKey")}
            </span>
            <code
              className="rounded-md bg-[var(--bg-muted)] px-2 py-1 font-mono text-sm text-[var(--text-primary)]"
            >
              {editing.key}
            </code>
          </div>
        ) : (
          <Input
            id="flag-key"
            label={t("sheet.labelKey")}
            value={form.key}
            onChange={(e) => patch({ key: e.target.value })}
            error={errors.key}
            help={t("sheet.labelKeyHelp")}
            placeholder="e.g. cv_studio.ai_fill"
            required
          />
        )}

        <Input
          id="flag-description"
          label={t("sheet.labelDescription")}
          value={form.description}
          onChange={(e) => patch({ description: e.target.value })}
          error={errors.description}
          help={t("sheet.labelDescriptionHelp")}
          placeholder="Brief description of what this flag controls"
        />

        <div>
          <Switch
            id="flag-enabled"
            checked={form.enabled}
            onCheckedChange={(checked) => patch({ enabled: checked })}
            label={t("sheet.labelEnabled")}
          />
          <p className="mt-1 text-xs text-[var(--text-muted)]">
            {t("sheet.labelEnabledHelp")}
          </p>
        </div>

        <div>
          <Input
            id="flag-rollout"
            type="number"
            inputMode="numeric"
            min={0}
            max={100}
            step={1}
            label={t("sheet.labelRollout")}
            value={form.rollout_percentage}
            onChange={(e) => patch({ rollout_percentage: e.target.value })}
            error={errors.rollout_percentage}
            help={t("sheet.labelRolloutHelp")}
            placeholder="100"
            required
          />
          <p className="mt-1 text-[0.6875rem] text-[var(--text-muted)]">
            {t("sheet.rolloutContext")}
          </p>
        </div>

        {errors.conflict && (
          <div className="flex items-start gap-2 rounded-xl bg-[var(--red-50)] px-3 py-2.5 text-sm text-[var(--brand-red)]">
            <Warning aria-hidden weight="fill" className="mt-0.5 size-4 shrink-0" />
            <p>{errors.conflict}</p>
          </div>
        )}

        <div className="flex items-center justify-end gap-3 pt-2">
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
            disabled={isPending}
          >
            {t("sheet.cancel")}
          </Button>
          <Button type="submit" variant="primary" loading={isPending}>
            {t("sheet.save")}
          </Button>
        </div>
      </form>
    </Sheet>
  );
}

/* -------------------------------------------------------------------------- */
/* Flags tab                                                                   */
/* -------------------------------------------------------------------------- */

function FlagsTab() {
  const t = useTranslations("adminConsole.featureFlags.flags");
  const tRoot = useTranslations("adminConsole.featureFlags");
  const toast = useToast();
  const qc = useQueryClient();

  const [sheetOpen, setSheetOpen] = useState(false);
  const [editingRow, setEditingRow] = useState<FeatureFlag | null>(null);

  const flagsQuery = useQuery({
    queryKey: ["feature-flags"] as const,
    queryFn: () => featureFlagsApi.list(),
    staleTime: 30_000,
    retry: 1,
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      featureFlagsApi.update(id, { enabled }),
    onSuccess: (updated) => {
      void qc.invalidateQueries({ queryKey: ["feature-flags"] });
      toast.show({
        tone: "success",
        title: updated.enabled ? t("enabledYes") : t("enabledNo"),
      });
    },
    onError: () => {
      toast.show({ tone: "error", title: tRoot("retry") });
    },
  });

  const flagRows = flagsQuery.data ?? [];

  const columns: Column<FeatureFlag>[] = [
    {
      key: "key",
      header: t("col.key"),
      cell: (row) => (
        <code className="rounded bg-[var(--bg-muted)] px-1.5 py-0.5 font-mono text-xs font-semibold text-[var(--text-primary)]">
          {row.key}
        </code>
      ),
    },
    {
      key: "description",
      header: t("col.description"),
      cell: (row) => (
        <span className="max-w-xs truncate text-sm text-[var(--text-secondary)]">
          {row.description || <span className="italic text-[var(--text-muted)]">—</span>}
        </span>
      ),
    },
    {
      key: "enabled",
      header: t("col.enabled"),
      cell: (row) => (
        <Switch
          id={`flag-toggle-${row.id}`}
          checked={row.enabled}
          onCheckedChange={(checked) => {
            toggleMutation.mutate({ id: row.id, enabled: checked });
          }}
          disabled={toggleMutation.isPending}
          label={row.enabled ? t("enabledYes") : t("enabledNo")}
          hideLabel
        />
      ),
    },
    {
      key: "rollout_percentage",
      header: t("col.rollout"),
      cell: (row) => (
        <RolloutBar pct={row.rollout_percentage} enabled={row.enabled} />
      ),
    },
    {
      key: "updated_by",
      header: t("col.updatedBy"),
      cell: (row) => (
        <span className="truncate text-xs text-[var(--text-muted)]">
          {row.updated_by ?? "—"}
        </span>
      ),
    },
    {
      key: "updated_at",
      header: t("col.updatedAt"),
      cell: (row) => (
        <span className="tabular-nums text-xs text-[var(--text-muted)]">
          {row.updated_at.slice(0, 10)}
        </span>
      ),
    },
    {
      key: "actions",
      header: t("col.actions"),
      align: "right",
      cell: (row) => (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setEditingRow(row);
            setSheetOpen(true);
          }}
          className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/50"
          aria-label={`${t("editAction")} ${row.key}`}
        >
          <PencilSimple aria-hidden weight="bold" className="size-3.5" />
          {t("editAction")}
        </button>
      ),
    },
  ];

  function handleAddClick() {
    setEditingRow(null);
    setSheetOpen(true);
  }

  function handleClose() {
    setSheetOpen(false);
    setEditingRow(null);
  }

  if (flagsQuery.isPending) {
    return (
      <div className="marketplace-card rounded-[12px] p-5">
        <FlagsTabHeader title={t("panelTitle")} onAdd={handleAddClick} addLabel={t("addFlag")} />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (flagsQuery.isError) {
    return (
      <div className="marketplace-card rounded-[12px] p-5">
        <FlagsTabHeader title={t("panelTitle")} onAdd={handleAddClick} addLabel={t("addFlag")} />
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("errorTitle")}
          description={t("errorBody")}
          action={
            <button
              onClick={() => void flagsQuery.refetch()}
              className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
            >
              {tRoot("retry")}
            </button>
          }
        />
      </div>
    );
  }

  return (
    <>
      <div className="marketplace-card rounded-[12px] p-5">
        <FlagsTabHeader title={t("panelTitle")} onAdd={handleAddClick} addLabel={t("addFlag")} />
        <DataTable
          columns={columns}
          rows={flagRows}
          getRowId={(r) => r.id}
          empty={{
            kind: "empty",
            title: t("emptyTitle"),
            description: t("emptyBody"),
          }}
          caption={t("panelTitle")}
        />
      </div>

      <FlagFormSheet
        open={sheetOpen}
        editing={editingRow}
        onClose={handleClose}
      />
    </>
  );
}

function FlagsTabHeader({
  title,
  onAdd,
  addLabel,
}: {
  title: string;
  onAdd: () => void;
  addLabel: string;
}) {
  return (
    <div className="mb-4 flex items-center justify-between gap-4">
      <h2 className="flex items-center gap-2 text-sm font-bold tracking-tight text-[var(--text-primary)]">
        <span className="icon-chip-primary flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm">
          <ToggleRight aria-hidden weight="duotone" className="size-4" />
        </span>
        {title}
      </h2>
      <Button variant="primary" onClick={onAdd}>
        <Plus aria-hidden weight="bold" className="size-4" />
        {addLabel}
      </Button>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Permissions tab                                                             */
/* -------------------------------------------------------------------------- */

function PermissionsTab() {
  const t = useTranslations("adminConsole.featureFlags.permissions");
  const tRoot = useTranslations("adminConsole.featureFlags");

  const catalogQuery = useQuery({
    queryKey: ["feature-flags", "permission-catalog"] as const,
    queryFn: async () => {
      const res = await featureFlagsApi.permissionCatalog();
      return res.catalog;
    },
    staleTime: 5 * 60_000,
    retry: 1,
  });

  const entries: PermissionCatalogEntry[] = catalogQuery.data ?? [];

  if (catalogQuery.isPending) {
    return (
      <div className="marketplace-card rounded-[12px] p-5">
        <PermissionsTabHeader />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (catalogQuery.isError) {
    return (
      <div className="marketplace-card rounded-[12px] p-5">
        <PermissionsTabHeader />
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("errorTitle")}
          description={t("errorBody")}
          action={
            <button
              onClick={() => void catalogQuery.refetch()}
              className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
            >
              {tRoot("retry")}
            </button>
          }
        />
      </div>
    );
  }

  if (entries.length === 0) {
    return (
      <div className="marketplace-card rounded-[12px] p-5">
        <PermissionsTabHeader />
        <EmptyState
          kind="empty"
          title={t("emptyTitle")}
          description={t("emptyBody")}
        />
      </div>
    );
  }

  return (
    <div className="marketplace-card rounded-[12px] p-5">
      <PermissionsTabHeader />
      <div
        className="overflow-x-auto rounded-xl border border-white/60 bg-white/82 backdrop-blur-md"
        role="table"
        aria-label={t("panelTitle")}
      >
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border-default)]">
              <th
                scope="col"
                className="px-4 py-3 text-left text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]"
              >
                {t("col.resource")}
              </th>
              <th
                scope="col"
                className="px-4 py-3 text-left text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]"
              >
                {t("col.actions")}
              </th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry, i) => (
              <tr
                key={entry.resource}
                className={
                  i % 2 === 0
                    ? "bg-transparent"
                    : "bg-[var(--bg-subtle)]/40"
                }
              >
                <td className="px-4 py-3 align-top">
                  <code className="rounded bg-[var(--bg-muted)] px-1.5 py-0.5 font-mono text-xs font-semibold text-[var(--text-primary)]">
                    {entry.resource}
                  </code>
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1.5">
                    {entry.actions.map((action) => (
                      <span
                        key={action}
                        className="inline-flex items-center rounded-full border border-[var(--border-default)] bg-[var(--bg-muted)] px-2 py-0.5 font-mono text-[0.6875rem] text-[var(--text-secondary)]"
                      >
                        {action}
                      </span>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PermissionsTabHeader() {
  const t = useTranslations("adminConsole.featureFlags.permissions");
  return (
    <div className="mb-4">
      <h2 className="flex items-center gap-2 text-sm font-bold tracking-tight text-[var(--text-primary)]">
        <span className="icon-chip-neutral flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm">
          <ShieldCheck aria-hidden weight="duotone" className="size-4" />
        </span>
        {t("panelTitle")}
      </h2>
      <p className="mt-1 text-xs text-[var(--text-muted)]">
        {t("panelSubtitle")}
      </p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Main screen                                                                 */
/* -------------------------------------------------------------------------- */

type FlagTab = "flags" | "permissions";

export function FeatureFlagsScreen() {
  const t = useTranslations("adminConsole.featureFlags");
  const tabsId = useId();
  const [tab, setTab] = useState<FlagTab>("flags");

  const tabItems: TabItem[] = [
    { value: "flags", label: t("tabs.flags") },
    { value: "permissions", label: t("tabs.permissions") },
  ];

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-xl font-bold tracking-tight text-[var(--text-primary)]">
          {t("pageTitle")}
        </h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          {t("pageSubtitle")}
        </p>
      </div>

      {/* Tabs */}
      <Tabs
        idBase={tabsId}
        items={tabItems}
        value={tab}
        onValueChange={(v) => setTab(v as FlagTab)}
        ariaLabel={t("pageTitle")}
      />

      <TabPanel tabsId={tabsId} value="flags" active={tab === "flags"}>
        <FlagsTab />
      </TabPanel>

      <TabPanel tabsId={tabsId} value="permissions" active={tab === "permissions"}>
        <PermissionsTab />
      </TabPanel>
    </div>
  );
}
