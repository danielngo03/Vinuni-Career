"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Modal, Textarea, Input, Button, useToast } from "@/components/ui";
import { aiGovernanceApi, ApiError } from "@/lib/api";

/**
 * University staff capacity-request dialog. University AI energy is DISTRIBUTION,
 * not billing — when a staff member exhausts their weekly allocation they cannot
 * self-serve upgrade; they submit a reason (+ an optional desired amount of
 * opaque energy credits) and a platform admin decides.
 *
 * On success the caller's usage meter and their capacity-request list are
 * invalidated so the pending state shows immediately. A duplicate pending
 * request surfaces the backend's 409 as an inline, non-destructive message.
 * Energy is opaque throughout — never tokens/cost/provider/model.
 */
export function CapacityRequestDialog({
  open,
  onClose,
  onSubmitted,
}: {
  open: boolean;
  onClose: () => void;
  onSubmitted?: () => void;
}) {
  const t = useTranslations("aiGovernance.dialog");
  const toast = useToast();
  const qc = useQueryClient();

  const [reason, setReason] = useState("");
  const [units, setUnits] = useState("");
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [unitsError, setUnitsError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  function reset() {
    setReason("");
    setUnits("");
    setReasonError(null);
    setUnitsError(null);
    setFormError(null);
  }

  const mutation = useMutation({
    mutationFn: () => {
      const trimmed = reason.trim();
      const parsed = units.trim() === "" ? null : Math.round(Number(units));
      return aiGovernanceApi.submitCapacityRequest({
        reason: trimmed,
        requested_units: parsed,
      });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["ai", "capacity-requests", "me"] });
      void qc.invalidateQueries({ queryKey: ["ai", "usage", "me"] });
      void qc.invalidateQueries({ queryKey: ["ai", "usage", "summary"] });
      toast.show({ tone: "success", title: t("successToast") });
      reset();
      onSubmitted?.();
      onClose();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.isConflict) {
        setFormError(t("alreadyPending"));
        return;
      }
      if (e instanceof ApiError && e.isValidation) {
        setFormError(e.message || t("error"));
        return;
      }
      setFormError(t("error"));
    },
  });

  function validate(): boolean {
    let ok = true;
    if (!reason.trim()) {
      setReasonError(t("reasonRequired"));
      ok = false;
    }
    if (units.trim() !== "") {
      const n = Number(units);
      if (!Number.isFinite(n) || n <= 0) {
        setUnitsError(t("unitsInvalid"));
        ok = false;
      }
    }
    return ok;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (!validate()) return;
    mutation.mutate();
  }

  function handleClose() {
    if (mutation.isPending) return;
    reset();
    onClose();
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title={t("title")}
      description={t("subtitle")}
      size="sm"
      closeLabel={t("cancel")}
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <Textarea
          id="capacity-reason"
          label={t("reasonLabel")}
          value={reason}
          onChange={(e) => {
            setReason(e.target.value);
            setReasonError(null);
            setFormError(null);
          }}
          error={reasonError ?? undefined}
          help={reasonError ? undefined : t("reasonHelp")}
          placeholder={t("reasonPlaceholder")}
          rows={4}
          required
          maxLength={2000}
        />

        <Input
          id="capacity-units"
          type="number"
          inputMode="numeric"
          min={1}
          step={1}
          label={`${t("unitsLabel")} · ${t("unitsOptional")}`}
          value={units}
          onChange={(e) => {
            setUnits(e.target.value);
            setUnitsError(null);
          }}
          error={unitsError ?? undefined}
          help={unitsError ? undefined : t("unitsHelp")}
          placeholder={t("unitsPlaceholder")}
        />

        {formError && (
          <p role="alert" className="text-sm font-medium text-[var(--brand-red)]">
            {formError}
          </p>
        )}

        <div className="flex items-center justify-end gap-3 pt-1">
          <Button
            type="button"
            variant="ghost"
            onClick={handleClose}
            disabled={mutation.isPending}
          >
            {t("cancel")}
          </Button>
          <Button type="submit" variant="primary" loading={mutation.isPending}>
            {t("submit")}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
