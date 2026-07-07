"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Tag, Warning, WarningCircle, Plus, PencilSimple } from "@phosphor-icons/react";
import {
  DataTable,
  Sheet,
  EmptyState,
  Skeleton,
  Button,
  Input,
  useToast,
  type Column,
} from "@/components/ui";
import {
  aiOpsApi,
  type AiOpsPrice,
  type AiOpsPriceCreateBody,
  type AiOpsPriceUpdateBody,
} from "@/lib/api/ai-ops";
import { ApiError } from "@/lib/api";
import { formatUsd } from "./ai-ops-helpers";

/* -------------------------------------------------------------------------- */
/* Helpers                                                                    */
/* -------------------------------------------------------------------------- */

function isValidCost(s: string): boolean {
  const n = parseFloat(s);
  return isFinite(n) && n >= 0;
}

/* -------------------------------------------------------------------------- */
/* Price form sheet                                                           */
/* -------------------------------------------------------------------------- */

interface PriceFormState {
  alias: string;
  prompt_cost_per_1k: string;
  completion_cost_per_1k: string;
  effective_from: string;
  effective_until: string;
  notes: string;
}

interface PriceFormErrors {
  alias?: string;
  prompt_cost_per_1k?: string;
  completion_cost_per_1k?: string;
  effective_from?: string;
  conflict?: string;
}

const EMPTY_FORM: PriceFormState = {
  alias: "",
  prompt_cost_per_1k: "",
  completion_cost_per_1k: "",
  effective_from: new Date().toISOString().slice(0, 10),
  effective_until: "",
  notes: "",
};

function priceToForm(p: AiOpsPrice): PriceFormState {
  return {
    alias: p.alias,
    prompt_cost_per_1k: p.prompt_cost_per_1k,
    completion_cost_per_1k: p.completion_cost_per_1k,
    effective_from: p.effective_from.slice(0, 10),
    effective_until: p.effective_until ? p.effective_until.slice(0, 10) : "",
    notes: p.notes ?? "",
  };
}

function PriceFormSheet({
  open,
  editing,
  onClose,
  onSaved,
}: {
  open: boolean;
  editing: AiOpsPrice | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const t = useTranslations("adminConsole.aiOps.pricing");
  const tAiOps = useTranslations("adminConsole.aiOps");
  const toast = useToast();

  const [form, setForm] = useState<PriceFormState>(
    editing ? priceToForm(editing) : EMPTY_FORM,
  );
  const [errors, setErrors] = useState<PriceFormErrors>({});

  function patch(partial: Partial<PriceFormState>) {
    setForm((f) => ({ ...f, ...partial }));
    // Clear relevant errors on change
    setErrors((e) => {
      const next = { ...e };
      for (const k of Object.keys(partial) as (keyof PriceFormState)[]) {
        delete (next as Record<string, string | undefined>)[k];
      }
      delete next.conflict;
      return next;
    });
  }

  function validate(): PriceFormErrors {
    const errs: PriceFormErrors = {};
    if (!editing && !form.alias.trim()) errs.alias = t("sheet.validationAlias");
    if (!isValidCost(form.prompt_cost_per_1k))
      errs.prompt_cost_per_1k = t("sheet.validationCost");
    if (!isValidCost(form.completion_cost_per_1k))
      errs.completion_cost_per_1k = t("sheet.validationCost");
    if (!form.effective_from.trim()) errs.effective_from = t("sheet.validationFrom");
    return errs;
  }

  const qc = useQueryClient();

  const createMutation = useMutation({
    mutationFn: (body: AiOpsPriceCreateBody) => aiOpsApi.createPrice(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["ai-ops", "prices"] });
      toast.show({ tone: "success", title: t("sheet.save") });
      onSaved();
      onClose();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.isConflict) {
        setErrors((prev) => ({ ...prev, conflict: t("sheet.conflictError") }));
        return;
      }
      toast.show({ tone: "error", title: tAiOps("retry") });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: AiOpsPriceUpdateBody }) =>
      aiOpsApi.updatePrice(id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["ai-ops", "prices"] });
      toast.show({ tone: "success", title: t("sheet.save") });
      onSaved();
      onClose();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.isConflict) {
        setErrors((prev) => ({ ...prev, conflict: t("sheet.conflictError") }));
        return;
      }
      toast.show({ tone: "error", title: tAiOps("retry") });
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

    if (editing) {
      const body: AiOpsPriceUpdateBody = {
        prompt_cost_per_1k: form.prompt_cost_per_1k,
        completion_cost_per_1k: form.completion_cost_per_1k,
        effective_from: form.effective_from,
        effective_until: form.effective_until || null,
        notes: form.notes || null,
      };
      updateMutation.mutate({ id: editing.id, body });
    } else {
      const body: AiOpsPriceCreateBody = {
        alias: form.alias.trim(),
        prompt_cost_per_1k: form.prompt_cost_per_1k,
        completion_cost_per_1k: form.completion_cost_per_1k,
        effective_from: form.effective_from,
        ...(form.effective_until ? { effective_until: form.effective_until } : {}),
        ...(form.notes ? { notes: form.notes } : {}),
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
        {/* Alias — read-only when editing */}
        {editing ? (
          <div>
            <span className="block text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)] mb-1">
              {t("sheet.labelAlias")}
            </span>
            <span
              className="font-mono text-sm text-[var(--text-primary)]"
              style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
            >
              {editing.alias}
            </span>
          </div>
        ) : (
          <Input
            id="price-alias"
            label={t("sheet.labelAlias")}
            value={form.alias}
            onChange={(e) => patch({ alias: e.target.value })}
            error={errors.alias}
            help={t("sheet.labelAliasHelp")}
            placeholder="e.g. chat_cheap"
            required
          />
        )}

        <Input
          id="price-prompt-cost"
          type="number"
          inputMode="decimal"
          min={0}
          step="any"
          label={t("sheet.labelPromptCost")}
          value={form.prompt_cost_per_1k}
          onChange={(e) => patch({ prompt_cost_per_1k: e.target.value })}
          error={errors.prompt_cost_per_1k}
          placeholder="0.0015"
          required
        />

        <Input
          id="price-completion-cost"
          type="number"
          inputMode="decimal"
          min={0}
          step="any"
          label={t("sheet.labelCompletionCost")}
          value={form.completion_cost_per_1k}
          onChange={(e) => patch({ completion_cost_per_1k: e.target.value })}
          error={errors.completion_cost_per_1k}
          placeholder="0.0020"
          required
        />

        <Input
          id="price-effective-from"
          type="date"
          label={t("sheet.labelEffectiveFrom")}
          value={form.effective_from}
          onChange={(e) => patch({ effective_from: e.target.value })}
          error={errors.effective_from}
          required
        />

        <Input
          id="price-effective-until"
          type="date"
          label={t("sheet.labelEffectiveUntil")}
          value={form.effective_until}
          onChange={(e) => patch({ effective_until: e.target.value })}
        />

        <Input
          id="price-notes"
          label={t("sheet.labelNotes")}
          value={form.notes}
          onChange={(e) => patch({ notes: e.target.value })}
          placeholder=""
        />

        {errors.conflict && (
          <div className="flex items-start gap-2 rounded-xl bg-[var(--red-50)] px-3 py-2.5 text-sm text-[var(--brand-red)]">
            <Warning aria-hidden weight="fill" className="size-4 mt-0.5 shrink-0" />
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
/* Unpriced aliases banner                                                    */
/* -------------------------------------------------------------------------- */

function UnpricedBanner({
  aliases,
  label,
}: {
  aliases: string[];
  label: string;
}) {
  if (aliases.length === 0) return null;
  return (
    <div className="mb-4 flex items-start gap-2 rounded-xl border border-[var(--amber-400)]/40 bg-[var(--amber-50)] px-4 py-3 text-sm text-[var(--amber-700)]">
      <Warning aria-hidden weight="fill" className="size-4 mt-0.5 shrink-0 text-[var(--amber-600)]" />
      <p>{label.replace("{aliases}", aliases.join(", "))}</p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Main pricing screen                                                        */
/* -------------------------------------------------------------------------- */

export function AiPricingScreen() {
  const t = useTranslations("adminConsole.aiOps.pricing");
  const tAiOps = useTranslations("adminConsole.aiOps");

  const [sheetOpen, setSheetOpen] = useState(false);
  const [editingRow, setEditingRow] = useState<AiOpsPrice | null>(null);

  const pricesQuery = useQuery({
    queryKey: ["ai-ops", "prices"] as const,
    queryFn: () => aiOpsApi.prices(),
    staleTime: 60_000,
    retry: 1,
  });

  // Load recent events to detect unpriced aliases (nice-to-have; non-blocking)
  const eventsQuery = useQuery({
    queryKey: ["ai-ops", "events", "today", undefined] as const,
    queryFn: () => aiOpsApi.events({ range: "today", limit: 200 }),
    staleTime: 60_000,
    retry: 0,
  });

  const priceRows = pricesQuery.data ?? [];
  const pricedAliases = new Set(priceRows.map((p) => p.alias));

  // Collect aliases with usage but no price row
  const unpricedAliases: string[] = (() => {
    if (!eventsQuery.data) return [];
    const seen = new Set<string>();
    const unpriced: string[] = [];
    for (const ev of eventsQuery.data.data) {
      if (!pricedAliases.has(ev.alias) && !seen.has(ev.alias)) {
        seen.add(ev.alias);
        unpriced.push(ev.alias);
      }
    }
    return unpriced;
  })();

  const columns: Column<AiOpsPrice>[] = [
    {
      key: "alias",
      header: t("col.alias"),
      cell: (row) => (
        <span
          className="font-mono text-xs font-semibold text-[var(--text-primary)]"
          style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
        >
          {row.alias}
        </span>
      ),
    },
    {
      key: "prompt_cost_per_1k",
      header: t("col.promptCost"),
      align: "right",
      cell: (row) => (
        <span
          className="font-mono text-xs tabular-nums text-[var(--text-secondary)]"
          style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
        >
          {formatUsd(row.prompt_cost_per_1k)}
        </span>
      ),
    },
    {
      key: "completion_cost_per_1k",
      header: t("col.completionCost"),
      align: "right",
      cell: (row) => (
        <span
          className="font-mono text-xs tabular-nums text-[var(--text-secondary)]"
          style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
        >
          {formatUsd(row.completion_cost_per_1k)}
        </span>
      ),
    },
    {
      key: "effective_from",
      header: t("col.effectiveFrom"),
      cell: (row) => (
        <span className="text-xs text-[var(--text-secondary)]">
          {row.effective_from.slice(0, 10)}
        </span>
      ),
    },
    {
      key: "effective_until",
      header: t("col.effectiveUntil"),
      cell: (row) => (
        <span className="text-xs text-[var(--text-muted)]">
          {row.effective_until ? row.effective_until.slice(0, 10) : "—"}
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
          aria-label={`${t("editAction")} ${row.alias}`}
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

  if (pricesQuery.isPending) {
    return (
      <div className="marketplace-card rounded-[12px] p-5">
        <PanelHeader title={t("panelTitle")} onAdd={handleAddClick} addLabel={t("addPrice")} />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (pricesQuery.isError) {
    return (
      <div className="marketplace-card rounded-[12px] p-5">
        <PanelHeader title={t("panelTitle")} onAdd={handleAddClick} addLabel={t("addPrice")} />
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("errorTitle")}
          description={t("errorBody")}
          action={
            <button
              onClick={() => void pricesQuery.refetch()}
              className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
            >
              {tAiOps("retry")}
            </button>
          }
        />
      </div>
    );
  }

  return (
    <>
      <div className="marketplace-card rounded-[12px] p-5">
        <PanelHeader title={t("panelTitle")} onAdd={handleAddClick} addLabel={t("addPrice")} />

        <UnpricedBanner
          aliases={unpricedAliases}
          label={t("unpricedBanner")}
        />

        <DataTable
          columns={columns}
          rows={priceRows}
          getRowId={(r) => r.id}
          empty={{
            kind: "empty",
            title: t("emptyTitle"),
            description: t("emptyBody"),
          }}
          caption={t("panelTitle")}
        />
      </div>

      <PriceFormSheet
        open={sheetOpen}
        editing={editingRow}
        onClose={handleClose}
        onSaved={() => {
          // invalidation already done in mutation onSuccess
        }}
      />
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Panel header helper                                                         */
/* -------------------------------------------------------------------------- */

function PanelHeader({
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
          <Tag aria-hidden weight="duotone" className="size-4" />
        </span>
        {title}
      </h2>
      <Button
        variant="primary"
        onClick={onAdd}
      >
        <Plus aria-hidden weight="bold" className="size-4" />
        {addLabel}
      </Button>
    </div>
  );
}
