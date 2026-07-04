"use client";

import { Button, Input, Modal } from "@/components/ui";
import { useBillingLabels } from "@/lib/billing/labels";
import type { BillingAudience } from "@/lib/api";
import { CheckboxField, LabeledTextarea, SelectField } from "./form-fields";
import type { PlanDialogKind, PlanForm } from "./utils";

export function PlanFormModal({
  planDialog,
  planForm,
  planError,
  saving,
  t,
  tc,
  onClose,
  onPatch,
  onSubmit,
}: {
  planDialog: PlanDialogKind;
  planForm: PlanForm;
  planError: string | null;
  saving: boolean;
  t: ReturnType<typeof import("next-intl").useTranslations>;
  tc: (key: string) => string;
  onClose: () => void;
  onPatch: (patch: Partial<PlanForm>) => void;
  onSubmit: () => void;
}) {
  const labels = useBillingLabels();

  return (
    <Modal
      open={planDialog !== null}
      onClose={onClose}
      title={planDialog === "edit" ? t("planEditTitle") : t("planCreateTitle")}
      description={t("planFormBody")}
      size="lg"
      closeLabel={tc("close")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button variant="primary" loading={saving} onClick={onSubmit}>
            {t("planSave")}
          </Button>
        </>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Input
          id="billing-plan-code"
          label={t("planCode")}
          value={planForm.code}
          disabled={planDialog === "edit"}
          onChange={(e) => onPatch({ code: e.target.value })}
        />
        <SelectField
          id="billing-plan-audience"
          label={t("planAudience")}
          value={planForm.audience}
          disabled={planDialog === "edit"}
          onChange={(value) => onPatch({ audience: value as BillingAudience })}
          options={[
            { value: "student", label: labels.audience("student") },
            { value: "partner", label: labels.audience("partner") },
          ]}
        />
        <Input
          id="billing-plan-name"
          label={t("planNameVi")}
          value={planForm.name}
          onChange={(e) => onPatch({ name: e.target.value })}
        />
        <Input
          id="billing-plan-name-en"
          label={t("planNameEn")}
          value={planForm.nameEn}
          onChange={(e) => onPatch({ nameEn: e.target.value })}
        />
        <SelectField
          id="billing-plan-period"
          label={t("planPeriod")}
          value={planForm.billingPeriod}
          onChange={(value) =>
            onPatch({ billingPeriod: value as "monthly" | "annual" })
          }
          options={[
            { value: "monthly", label: labels.period("monthly") },
            { value: "annual", label: labels.period("annual") },
          ]}
        />
        <Input
          id="billing-plan-duration"
          label={t("planDuration")}
          type="number"
          min={1}
          value={planForm.durationDays}
          onChange={(e) => onPatch({ durationDays: e.target.value })}
        />
        <Input
          id="billing-plan-price"
          label={t("planPrice")}
          type="number"
          min={0}
          step="1000"
          value={planForm.priceAmount}
          onChange={(e) => onPatch({ priceAmount: e.target.value })}
        />
        <Input
          id="billing-plan-currency"
          label={t("planCurrency")}
          value={planForm.currency}
          onChange={(e) => onPatch({ currency: e.target.value })}
        />
        <Input
          id="billing-plan-sort"
          label={t("planSortOrder")}
          type="number"
          value={planForm.sortOrder}
          onChange={(e) => onPatch({ sortOrder: e.target.value })}
        />
        <div className="flex items-center gap-4 pt-6">
          <CheckboxField
            id="billing-plan-visible"
            label={t("planVisible")}
            checked={planForm.isVisible}
            onChange={(checked) => onPatch({ isVisible: checked })}
          />
          <CheckboxField
            id="billing-plan-default"
            label={t("planDefault")}
            checked={planForm.isDefault}
            onChange={(checked) => onPatch({ isDefault: checked })}
          />
        </div>
        <div className="sm:col-span-2">
          <LabeledTextarea
            id="billing-plan-limits"
            label={t("planLimits")}
            value={planForm.limitsText}
            onChange={(value) => onPatch({ limitsText: value })}
            hint={t("planLimitsHint")}
            error={planError ?? undefined}
            rows={8}
          />
        </div>
      </div>
    </Modal>
  );
}
