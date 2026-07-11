"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { Button, Modal, useToast } from "@/components/ui";
import { ApiError, applicationsApi, type Interview, type InterviewOutcome } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

export function CompleteModal({
  applicationId,
  interview,
  onClose,
  onSuccess,
  onConflict,
}: {
  applicationId: string;
  interview: Interview;
  onClose: () => void;
  onSuccess: (outcome: InterviewOutcome) => void;
  onConflict: () => void;
}) {
  const t = useTranslations("interviews");
  const tc = useTranslations("common");
  const toast = useToast();
  const apiError = useApiErrorMessage();
  const [outcome, setOutcome] = useState<InterviewOutcome>("completed");

  const run = useMutation({
    mutationFn: () =>
      applicationsApi.completeInterview(
        applicationId,
        interview.id,
        outcome,
        interview.version,
      ),
    onSuccess: () => onSuccess(outcome),
    onError: (e) => {
      if (e instanceof ApiError && e.isConflict) return onConflict();
      toast.show({ tone: "error", title: apiError(e) });
    },
  });

  const options: { value: InterviewOutcome; label: string }[] = [
    { value: "completed", label: t("outcomeCompleted") },
    { value: "no_show", label: t("outcomeNoShow") },
  ];

  return (
    <Modal
      open
      onClose={run.isPending ? () => {} : onClose}
      title={t("completeTitle")}
      description={t("completeDescription")}
      size="sm"
      closeLabel={tc("close")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={run.isPending}>
            {tc("cancel")}
          </Button>
          <Button
            variant="primary"
            loading={run.isPending}
            onClick={() => run.mutate()}
          >
            {t("completeSubmit")}
          </Button>
        </>
      }
    >
      <fieldset className="space-y-2" disabled={run.isPending}>
        <legend className="mb-1 type-small font-semibold text-foreground">
          {t("outcomeLabel")}
        </legend>
        <div role="radiogroup" aria-label={t("outcomeLabel")} className="space-y-2">
          {options.map((o) => {
            const id = `complete-${o.value}`;
            return (
              <label
                key={o.value}
                htmlFor={id}
                className="flex cursor-pointer items-center gap-2.5 rounded-lg border border-border bg-[var(--bg-subtle)] px-3 py-2 type-small has-[:checked]:border-[var(--brand-primary)] has-[:checked]:bg-[var(--brand-primary)]/10 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-[var(--field-focus-border)]"
              >
                <input
                  id={id}
                  type="radio"
                  name="interview-outcome"
                  value={o.value}
                  checked={outcome === o.value}
                  onChange={() => setOutcome(o.value)}
                  className="size-4 accent-[var(--brand-primary)]"
                />
                <span className="text-foreground">{o.label}</span>
              </label>
            );
          })}
        </div>
      </fieldset>
    </Modal>
  );
}
