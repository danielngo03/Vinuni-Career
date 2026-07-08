"use client";

import { useTranslations } from "next-intl";
import {
  Button,
  Modal,
  Select,
  Textarea,
  type SelectOption,
} from "@/components/ui";
import { REJECTION_REASONS, type RejectionReason } from "@/lib/api";
import { useRejectionReasonLabel } from "@/lib/applications/labels";

export function RejectModal({
  open,
  onClose,
  reason,
  onReasonChange,
  note,
  onNoteChange,
  fieldError,
  loading,
  onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  reason: RejectionReason | "";
  onReasonChange: (v: RejectionReason | "") => void;
  note: string;
  onNoteChange: (v: string) => void;
  fieldError: string | null;
  loading: boolean;
  onSubmit: () => void;
}) {
  const t = useTranslations("candidates");
  const tc = useTranslations("common");
  const reasonLabel = useRejectionReasonLabel();

  const options: SelectOption[] = [
    { value: "", label: t("rejectReasonPlaceholder") },
    ...REJECTION_REASONS.map((code) => ({
      value: code,
      label: reasonLabel(code),
    })),
  ];

  return (
    <Modal
      open={open}
      onClose={loading ? () => {} : onClose}
      title={t("rejectTitle")}
      description={t("rejectDescription")}
      size="sm"
      closeLabel={tc("close")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            {tc("cancel")}
          </Button>
          <Button
            variant="danger"
            loading={loading}
            disabled={!reason || loading}
            onClick={onSubmit}
          >
            {t("rejectSubmit")}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Select
          label={t("rejectReasonLabel")}
          required
          options={options}
          value={reason}
          error={fieldError ?? undefined}
          onChange={(e) => onReasonChange(e.target.value as RejectionReason | "")}
        />
        <Textarea
          label={t("rejectNoteLabel")}
          rows={3}
          maxLength={500}
          value={note}
          placeholder={t("rejectNotePlaceholder")}
          help={t("partnerOnlyNote")}
          onChange={(e) => onNoteChange(e.target.value)}
        />
      </div>
    </Modal>
  );
}
