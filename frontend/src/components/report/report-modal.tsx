"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { Modal, Button, Select, Textarea, useToast } from "@/components/ui";
import {
  abuseApi,
  REPORT_REASON_CODES,
  type ReportEntityType,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

export interface ReportModalProps {
  open: boolean;
  onClose: () => void;
  entityType: ReportEntityType;
  entityId: string;
  /** Short label of the reported thing, e.g. the company/job title, for the confirmation copy. */
  entityLabel?: string;
}

/**
 * Generic "Report" flow shared by company/job/message surfaces
 * (ADR-0014 §Abuse & Content Reports). Posts to `/content-reports`; a
 * duplicate report from the same user on the same entity is idempotent
 * (`already_reported`), surfaced as a normal confirmation, not an error.
 */
export function ReportModal({
  open,
  onClose,
  entityType,
  entityId,
  entityLabel,
}: ReportModalProps) {
  const t = useTranslations("report");
  const tc = useTranslations("common");
  const toast = useToast();
  const getMessage = useApiErrorMessage();

  const [reasonCode, setReasonCode] = useState<string>("");
  const [note, setNote] = useState("");
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  function reset() {
    setReasonCode("");
    setNote("");
    setReasonError(null);
    setDone(false);
  }

  function handleClose() {
    reset();
    onClose();
  }

  const submit = useMutation({
    mutationFn: () => abuseApi.submitReport(entityType, entityId, reasonCode, note.trim() || undefined),
    onSuccess: () => setDone(true),
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  function onSubmit() {
    if (!reasonCode) {
      setReasonError(t("reasonRequired"));
      return;
    }
    setReasonError(null);
    submit.mutate();
  }

  const reasonOptions = REPORT_REASON_CODES.map((code) => ({
    value: code,
    label: t(`reasons.${code}`),
  }));

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title={t("title")}
      description={entityLabel ? t("descriptionWithEntity", { entity: entityLabel }) : t("description")}
      size="sm"
      closeLabel={tc("close")}
      footer={
        done ? (
          <Button variant="primary" onClick={handleClose}>
            {tc("done")}
          </Button>
        ) : (
          <>
            <Button variant="ghost" onClick={handleClose}>
              {tc("cancel")}
            </Button>
            <Button variant="danger" loading={submit.isPending} onClick={onSubmit}>
              {t("submit")}
            </Button>
          </>
        )
      }
    >
      {done ? (
        <p className="text-sm text-[var(--text-secondary)]">
          {submit.data?.status === "already_reported" ? t("alreadyReported") : t("submitted")}
        </p>
      ) : (
        <div className="space-y-4">
          <Select
            label={t("reasonLabel")}
            required
            value={reasonCode}
            onChange={(e) => {
              setReasonCode(e.target.value);
              if (e.target.value) setReasonError(null);
            }}
            options={[{ value: "", label: t("reasonPlaceholder"), disabled: true }, ...reasonOptions]}
            error={reasonError ?? undefined}
          />
          <Textarea
            label={t("noteLabel")}
            help={t("noteHelp")}
            value={note}
            maxLength={2000}
            rows={4}
            onChange={(e) => setNote(e.target.value)}
          />
          <p className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-subtle)] px-3 py-2 text-xs text-[var(--text-muted)]">
            {t("loggedNotice")}
          </p>
        </div>
      )}
    </Modal>
  );
}
