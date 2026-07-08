"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import {
  Button,
  Input,
  Modal,
  Select,
  Textarea,
  useToast,
  type SelectOption,
} from "@/components/ui";
import { useOfferLabels } from "@/lib/applications/labels";
import {
  ApiError,
  applicationsApi,
  SALARY_CURRENCIES,
  SALARY_PERIODS,
  type CreateOfferBody,
  type PartnerOffer,
  type UpdateOfferBody,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import {
  EMPTY_OFFER_FORM,
  localToIso,
  toDateInput,
  toLocalInput,
  type OfferFormState,
} from "./utils";

export function OfferFormModal({
  open,
  mode,
  applicationId,
  offer,
  onClose,
  onDone,
  onHandledConflict,
}: {
  open: boolean;
  mode: "create" | "edit";
  applicationId: string;
  offer?: PartnerOffer;
  onClose: () => void;
  onDone: (toastKey: "createdToast" | "updatedToast") => void;
  onHandledConflict: (e: unknown) => void;
}) {
  const t = useTranslations("offers");
  const tc = useTranslations("common");
  const labels = useOfferLabels();
  const toast = useToast();
  const apiError = useApiErrorMessage();

  const [form, setForm] = useState<OfferFormState>(EMPTY_OFFER_FORM);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!open) return;
    if (mode === "edit" && offer) {
      setForm({
        positionTitle: offer.position_title ?? "",
        department: offer.department ?? "",
        startDate: toDateInput(offer.start_date),
        salaryAmount:
          offer.salary_amount != null ? String(offer.salary_amount) : "",
        salaryCurrency: offer.salary_currency || "VND",
        salaryPeriod: offer.salary_period || "monthly",
        benefits: offer.benefits_summary ?? "",
        terms: offer.terms_notes ?? "",
        expiry: toLocalInput(offer.expiry_date),
      });
    } else {
      setForm(EMPTY_OFFER_FORM);
    }
    setFieldErrors({});
  }, [open, mode, offer]);

  function update<K extends keyof OfferFormState>(
    key: K,
    value: OfferFormState[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setFieldErrors((prev) => {
      if (!prev[key]) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }

  const submit = useMutation({
    mutationFn: () => {
      const expiryIso = localToIso(form.expiry);
      const amount = form.salaryAmount.trim()
        ? Number(form.salaryAmount)
        : null;
      if (mode === "edit" && offer) {
        const body: UpdateOfferBody = {
          position_title: form.positionTitle.trim(),
          department: form.department.trim() || null,
          start_date: form.startDate || null,
          salary_amount: amount,
          salary_currency: form.salaryCurrency,
          salary_period: form.salaryPeriod,
          benefits_summary: form.benefits.trim() || null,
          terms_notes: form.terms.trim() || null,
          expiry_date: expiryIso ?? undefined,
          version: offer.version,
        };
        return applicationsApi.updateOfferDraft(applicationId, offer.id, body);
      }
      const body: CreateOfferBody = {
        position_title: form.positionTitle.trim(),
        expiry_date: expiryIso as string,
        department: form.department.trim() || null,
        start_date: form.startDate || null,
        salary_amount: amount,
        salary_currency: form.salaryCurrency,
        salary_period: form.salaryPeriod,
        benefits_summary: form.benefits.trim() || null,
        terms_notes: form.terms.trim() || null,
      };
      return applicationsApi.createOffer(applicationId, body);
    },
    onSuccess: () => onDone(mode === "edit" ? "updatedToast" : "createdToast"),
    onError: (e) => {
      if (e instanceof ApiError) {
        if (e.isValidation) {
          const field =
            typeof e.details?.field === "string" ? e.details.field : null;
          if (field === "position_title") {
            setFieldErrors((prev) => ({
              ...prev,
              positionTitle: t("positionRequired"),
            }));
            return;
          }
          setFieldErrors((prev) => ({ ...prev, _form: t("fieldInvalid") }));
          return;
        }
        if (e.isConflict) {
          // offer_exists / offer_not_editable / version_conflict / illegal_transition
          onHandledConflict(e);
          return;
        }
      }
      toast.show({ tone: "error", title: apiError(e) });
    },
  });

  function validate(): boolean {
    const errs: Record<string, string> = {};
    if (!form.positionTitle.trim()) errs.positionTitle = t("positionRequired");
    if (!form.expiry || !localToIso(form.expiry)) {
      errs.expiry = t("deadlineRequired");
    }
    if (form.salaryAmount.trim()) {
      const n = Number(form.salaryAmount);
      if (Number.isNaN(n) || n < 0) errs.salaryAmount = t("salaryInvalid");
    }
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  }

  function handleSubmit() {
    if (!validate()) return;
    submit.mutate();
  }

  const currencyOptions: SelectOption[] = SALARY_CURRENCIES.map((c) => ({
    value: c,
    label: c,
  }));
  const periodOptions: SelectOption[] = SALARY_PERIODS.map((p) => ({
    value: p,
    label: labels.period(p),
  }));

  return (
    <Modal
      open={open}
      onClose={submit.isPending ? () => {} : onClose}
      title={mode === "edit" ? t("editTitle") : t("createTitle")}
      description={
        mode === "edit" ? t("editDescription") : t("createDescription")
      }
      size="md"
      closeLabel={tc("close")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submit.isPending}>
            {tc("cancel")}
          </Button>
          <Button
            variant="primary"
            loading={submit.isPending}
            onClick={handleSubmit}
          >
            {mode === "edit" ? t("editSubmit") : t("createSubmit")}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input
          label={t("positionLabel")}
          required
          maxLength={255}
          value={form.positionTitle}
          error={fieldErrors.positionTitle}
          placeholder={t("positionPlaceholder")}
          onChange={(e) => update("positionTitle", e.target.value)}
        />

        <Input
          label={t("departmentLabel")}
          maxLength={200}
          value={form.department}
          placeholder={t("departmentPlaceholder")}
          onChange={(e) => update("department", e.target.value)}
        />

        {/* Comp: amount + currency + period. Salary is recruiter+student only. */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input
            type="number"
            label={t("salaryLabel")}
            min={0}
            step={1}
            value={form.salaryAmount}
            error={fieldErrors.salaryAmount}
            help={t("salaryHelp")}
            placeholder={t("salaryPlaceholder")}
            onChange={(e) => update("salaryAmount", e.target.value)}
          />
          <div className="grid grid-cols-2 gap-2">
            <Select
              label={t("currencyLabel")}
              options={currencyOptions}
              value={form.salaryCurrency}
              onChange={(e) => update("salaryCurrency", e.target.value)}
            />
            <Select
              label={t("periodLabel")}
              options={periodOptions}
              value={form.salaryPeriod}
              onChange={(e) => update("salaryPeriod", e.target.value)}
            />
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input
            type="date"
            label={t("startDateLabel")}
            value={form.startDate}
            help={t("startDateHelp")}
            onChange={(e) => update("startDate", e.target.value)}
          />
          <Input
            type="datetime-local"
            label={t("deadlineLabel")}
            required
            value={form.expiry}
            error={fieldErrors.expiry}
            help={t("deadlineHelp")}
            onChange={(e) => update("expiry", e.target.value)}
          />
        </div>

        <Textarea
          label={t("benefitsLabel")}
          rows={2}
          maxLength={5000}
          value={form.benefits}
          placeholder={t("benefitsPlaceholder")}
          help={t("benefitsHelp")}
          onChange={(e) => update("benefits", e.target.value)}
        />

        <Textarea
          label={t("termsLabel")}
          rows={2}
          maxLength={5000}
          value={form.terms}
          placeholder={t("termsPlaceholder")}
          onChange={(e) => update("terms", e.target.value)}
        />

        {fieldErrors._form && (
          <p role="alert" className="text-xs font-medium text-[var(--brand-red)]">
            {fieldErrors._form}
          </p>
        )}
      </div>
    </Modal>
  );
}
