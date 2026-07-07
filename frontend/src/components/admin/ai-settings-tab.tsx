"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { BuildingOffice } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Input, Button } from "@/components/ui";
import { useToast } from "@/components/ui";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { AiSettingsScreen } from "@/components/ai-settings/ai-settings-screen";
import { aiSettingsApi } from "@/lib/api/ai-settings";

/* -------------------------------------------------------------------------- */
/* Per-organisation daily budget control                                      */
/* -------------------------------------------------------------------------- */

/**
 * Per-org daily budget control.
 *
 * Initialised from `per_org_daily_budget_usd` returned by GET /admin/ai-settings.
 * Save calls PATCH with `per_org_daily_budget_usd` (number) or
 * `clear_per_org_budget: true` when the input is empty (clears the cap).
 * Toasts on success/error; invalidates the shared ["admin","ai-settings"] query.
 */
function PerOrgBudgetControl() {
  const t = useTranslations("adminConsole.aiOps.settings");
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  /* Fetch the current settings — same query key used by AiSettingsScreen so
     the cache is shared and invalidation refreshes both panels. */
  const { data: settings, isLoading } = useQuery({
    queryKey: ["admin", "ai-settings"],
    queryFn: () => aiSettingsApi.get(),
  });

  const [value, setValue] = useState<string>("");
  const [dirty, setDirty] = useState(false);

  /* Initialise the input once the settings load (and reset when they refresh). */
  useEffect(() => {
    if (settings) {
      setValue(settings.per_org_daily_budget_usd ?? "");
      setDirty(false);
    }
  }, [settings]);

  const save = useMutation({
    mutationFn: () => {
      const trimmed = value.trim();
      if (trimmed === "") {
        return aiSettingsApi.update({ clear_per_org_budget: true });
      }
      const num = parseFloat(trimmed);
      return aiSettingsApi.update({ per_org_daily_budget_usd: num });
    },
    onSuccess: (updated) => {
      qc.setQueryData(["admin", "ai-settings"], updated);
      setDirty(false);
      toast.show({ tone: "success", title: t("perOrgSaved") });
    },
    onError: (e: unknown) => {
      toast.show({ tone: "error", title: getMessage(e) || t("perOrgError") });
    },
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setValue(e.target.value);
    setDirty(true);
  };

  /* Validate: empty (= clear) is allowed; otherwise must be a non-negative number. */
  const trimmed = value.trim();
  const isValid =
    trimmed === "" || (Number.isFinite(parseFloat(trimmed)) && parseFloat(trimmed) >= 0);

  return (
    <section
      className="rounded-2xl border border-white/60 bg-white/82 p-5 backdrop-blur-md shadow-[0_2px_12px_rgba(11,34,57,0.06)]"
      aria-labelledby="per-org-budget-heading"
    >
      <div className="mb-4 flex items-start gap-2.5">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-lg icon-chip-success shadow-sm">
          <BuildingOffice aria-hidden weight="duotone" className="size-4 text-white" />
        </span>
        <h2
          id="per-org-budget-heading"
          className="text-base font-bold text-[var(--text-primary)]"
        >
          {t("panelTitle")} — {t("perOrgBudgetLabel")}
        </h2>
      </div>

      <div className="max-w-xs">
        <Input
          id="ai-per-org-budget"
          type="number"
          inputMode="decimal"
          min={0}
          max={10000}
          step="0.01"
          label={t("perOrgBudgetLabel")}
          value={value}
          onChange={handleChange}
          help={t("perOrgBudgetHelp")}
          placeholder={isLoading ? t("loading") : t("perOrgBudgetPlaceholder")}
          disabled={isLoading || save.isPending}
        />
      </div>

      <div className="mt-4">
        <Button
          variant="secondary"
          disabled={isLoading || save.isPending || !dirty || !isValid}
          aria-disabled={isLoading || save.isPending || !dirty || !isValid}
          onClick={() => save.mutate()}
        >
          {save.isPending ? t("loading") : t("perOrgSaveLabel")}
        </Button>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/* AI Settings tab — wraps the existing AiSettingsScreen + per-org control   */
/* -------------------------------------------------------------------------- */

/**
 * Renders the full AI Settings panel inside the AI Operations tab shell.
 *
 * The existing `AiSettingsScreen` renders its own PageHeader and save bar.
 * The per-org budget control below it reads from the same cached query and
 * PATCHes `per_org_daily_budget_usd` on save.
 */
export function AiSettingsTab() {
  return (
    <div className="space-y-6">
      {/* Existing platform-wide AI settings (providers, aliases, rollout,
          kill switch, daily_budget_usd). Rendered as-is — it already handles
          its own loading/error/dirty states and save bar. */}
      <AiSettingsScreen />

      {/* Per-org daily budget — wired to per_org_daily_budget_usd field */}
      <PerOrgBudgetControl />
    </div>
  );
}
