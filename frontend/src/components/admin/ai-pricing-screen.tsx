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
  provider: string;
  model: string;
  input_usd_per_1k: string;
  output_usd_per_1k: string;
  active: boolean;
}

interface PriceFormErrors {
  provider?: string;
  model?: string;
  input_usd_per_1k?: string;
  output_usd_per_1k?: string;
  conflict?: string;
}

const EMPTY_FORM: PriceFormState = {
  provider: "",
  model: "",
  input_usd_per_1k: "",
  output_usd_per_1k: "",
  active: true,
};

function priceToForm(p: AiOpsPrice): PriceFormState {
  return {
    provider: p.provider,
    model: p.model,
    input_usd_per_1k: String(p.input_usd_per_1k),
    output_usd_per_1k: String(p.output_usd_per_1k),
    active: p.active,
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
    if (!editing && !form.provider.trim()) errs.provider = t("sheet.validationProvider");
    if (!editing && !form.model.trim()) errs.model = t("sheet.validationModel");
    if (!isValidCost(form.input_usd_per_1k))
      errs.input_usd_per_1k = t("sheet.validationCost");
    if (!isValidCost(form.output_usd_per_1k))
      errs.output_usd_per_1k = t("sheet.validationCost");
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

    const inputCost = parseFloat(form.input_usd_per_1k);
    const outputCost = parseFloat(form.output_usd_per_1k);

    if (editing) {
      const body: AiOpsPriceUpdateBody = {
        input_usd_per_1k: inputCost,
        output_usd_per_1k: outputCost,
        active: form.active,
      };
      updateMutation.mutate({ id: editing.id, body });
    } else {
      const body: AiOpsPriceCreateBody = {
        provider: form.provider.trim(),
        model: form.model.trim(),
        input_usd_per_1k: inputCost,
        output_usd_per_1k: outputCost,
        active: form.active,
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
        {/* Provider — read-only when editing */}
        {editing ? (
          <div>
            <span className="block text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)] mb-1">
              {t("sheet.labelProvider")}
            </span>
            <span
              className="font-mono text-sm text-[var(--text-primary)]"
              style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
            >
              {editing.provider}
            </span>
          </div>
        ) : (
          <Input
            id="price-provider"
            label={t("sheet.labelProvider")}
            value={form.provider}
            onChange={(e) => patch({ provider: e.target.value })}
            error={errors.provider}
            help={t("sheet.labelProviderHelp")}
            placeholder="e.g. openrouter"
            required
          />
        )}

        {/* Model — read-only when editing */}
        {editing ? (
          <div>
            <span className="block text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)] mb-1">
              {t("sheet.labelModel")}
            </span>
            <span
              className="font-mono text-sm text-[var(--text-primary)]"
              style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
            >
              {editing.model}
            </span>
          </div>
        ) : (
          <Input
            id="price-model"
            label={t("sheet.labelModel")}
            value={form.model}
            onChange={(e) => patch({ model: e.target.value })}
            error={errors.model}
            help={t("sheet.labelModelHelp")}
            placeholder="e.g. deepseek/deepseek-v3"
            required
          />
        )}

        <Input
          id="price-input-cost"
          type="number"
          inputMode="decimal"
          min={0}
          step="any"
          label={t("sheet.labelInputCost")}
          value={form.input_usd_per_1k}
          onChange={(e) => patch({ input_usd_per_1k: e.target.value })}
          error={errors.input_usd_per_1k}
          placeholder="0.0015"
          required
        />

        <Input
          id="price-output-cost"
          type="number"
          inputMode="decimal"
          min={0}
          step="any"
          label={t("sheet.labelOutputCost")}
          value={form.output_usd_per_1k}
          onChange={(e) => patch({ output_usd_per_1k: e.target.value })}
          error={errors.output_usd_per_1k}
          placeholder="0.0020"
          required
        />

        {/* Active toggle */}
        <div className="flex items-center gap-3">
          <input
            id="price-active"
            type="checkbox"
            checked={form.active}
            onChange={(e) => patch({ active: e.target.checked })}
            className="size-4 rounded border-[var(--border-default)] text-[var(--brand-primary)] focus:ring-[var(--brand-primary)]/50"
          />
          <label htmlFor="price-active" className="text-sm text-[var(--text-primary)]">
            {t("sheet.labelActive")}
          </label>
        </div>

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

  const priceRows = pricesQuery.data ?? [];

  const columns: Column<AiOpsPrice>[] = [
    {
      key: "provider",
      header: t("col.provider"),
      cell: (row) => (
        <span
          className="font-mono text-xs font-semibold text-[var(--text-primary)]"
          style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
        >
          {row.provider}
        </span>
      ),
    },
    {
      key: "model",
      header: t("col.model"),
      cell: (row) => (
        <span
          className="font-mono text-xs text-[var(--text-secondary)]"
          style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
        >
          {row.model}
        </span>
      ),
    },
    {
      key: "input_usd_per_1k",
      header: t("col.inputCost"),
      align: "right",
      cell: (row) => (
        <span
          className="font-mono text-xs tabular-nums text-[var(--text-secondary)]"
          style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
        >
          {formatUsd(row.input_usd_per_1k)}
        </span>
      ),
    },
    {
      key: "output_usd_per_1k",
      header: t("col.outputCost"),
      align: "right",
      cell: (row) => (
        <span
          className="font-mono text-xs tabular-nums text-[var(--text-secondary)]"
          style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
        >
          {formatUsd(row.output_usd_per_1k)}
        </span>
      ),
    },
    {
      key: "active",
      header: t("col.active"),
      cell: (row) => (
        <span
          className={
            row.active
              ? "text-xs font-semibold text-[var(--green-700)]"
              : "text-xs text-[var(--text-muted)]"
          }
        >
          {row.active ? t("activeYes") : t("activeNo")}
        </span>
      ),
    },
    {
      key: "updated_at",
      header: t("col.updatedAt"),
      cell: (row) => (
        <span className="text-xs text-[var(--text-muted)]">
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
          aria-label={`${t("editAction")} ${row.provider}/${row.model}`}
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
