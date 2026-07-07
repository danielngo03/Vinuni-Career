"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { BuildingOffice } from "@phosphor-icons/react";
import { Input, Button } from "@/components/ui";
import { AiSettingsScreen } from "@/components/ai-settings/ai-settings-screen";

/* -------------------------------------------------------------------------- */
/* Per-organisation daily budget control                                      */
/* -------------------------------------------------------------------------- */

/**
 * Per-org daily budget control.
 *
 * The backend field `per_org_daily_budget_usd` is not yet exposed on
 * GET/PATCH /admin/ai-settings (the AiSettings interface currently only has
 * `daily_budget_usd` which is the platform-wide cap). This control renders
 * with a clear TODO note and allows the admin to see and enter the value,
 * but the save action is intentionally inert until the backend exposes the
 * field. The note text is i18n-backed via adminConsole.aiOps.settings.
 */
function PerOrgBudgetControl() {
  const t = useTranslations("adminConsole.aiOps.settings");

  const [value, setValue] = useState<string>("");

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
          onChange={(e) => setValue(e.target.value)}
          help={t("perOrgBudgetHelp")}
          placeholder={t("perOrgBudgetPlaceholder")}
        />
      </div>

      {/* TODO note — visible to admin only; indicates pending backend wiring */}
      <p className="mt-3 text-xs text-[var(--text-muted)] italic">
        {t("perOrgBudgetNote")}
      </p>

      <div className="mt-4">
        <Button
          variant="secondary"
          disabled
          aria-disabled="true"
          title={t("perOrgBudgetNote")}
        >
          {t("perOrgSaveLabel")}
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
 * The existing `AiSettingsScreen` renders its own PageHeader and save bar, so
 * we wrap it with a thin container and append the per-org budget control below
 * the existing sections. The per-org control is a labeled input that PATCHes
 * `per_org_daily_budget_usd`; currently rendered as a clearly-labeled TODO
 * control pending backend field exposure.
 */
export function AiSettingsTab() {
  return (
    <div className="space-y-6">
      {/* Existing platform-wide AI settings (providers, aliases, rollout,
          kill switch, daily_budget_usd). Rendered as-is — it already handles
          its own loading/error/dirty states and save bar. */}
      <AiSettingsScreen />

      {/* Per-org daily budget — new control, not yet wired to backend field */}
      <PerOrgBudgetControl />
    </div>
  );
}
