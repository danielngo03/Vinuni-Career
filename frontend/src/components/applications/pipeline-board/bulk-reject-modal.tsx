"use client";

import { useTranslations } from "next-intl";
import { Prohibit } from "@phosphor-icons/react";
import {
  Button,
  Modal,
  Select,
  Textarea,
  type SelectOption,
} from "@/components/ui";
import { REJECTION_REASONS, type RejectionReason } from "@/lib/api";
import { useRejectionReasonLabel } from "@/lib/applications/labels";

export function BulkRejectModal({
  open,
  count,
  reason,
  note,
  loading,
  onReasonChange,
  onNoteChange,
  onClose,
  onSubmit,
  t,
}: {
  open: boolean;
  count: number;
  reason: RejectionReason;
  note: string;
  loading: boolean;
  onReasonChange: (r: RejectionReason) => void;
  onNoteChange: (n: string) => void;
  onClose: () => void;
  onSubmit: () => void;
  t: ReturnType<typeof useTranslations>;
}) {
  const tc = useTranslations("common");
  const rejectionLabel = useRejectionReasonLabel();
  const reasonOptions: SelectOption[] = REJECTION_REASONS.map((r) => ({
    value: r,
    label: rejectionLabel(r),
  }));

  return (
    <Modal
      open={open}
      onClose={loading ? () => {} : onClose}
      title={t("bulkRejectTitle")}
      description={t("bulkRejectDescription", { count })}
      size="sm"
      closeLabel={tc("close")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            {tc("cancel")}
          </Button>
          <Button variant="danger" loading={loading} onClick={onSubmit}>
            <Prohibit aria-hidden weight="bold" className="size-4" />
            {t("bulkRejectSubmit", { count })}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Select
          label={t("bulkRejectReasonLabel")}
          required
          options={reasonOptions}
          value={reason}
          onChange={(e) => onReasonChange(e.target.value as RejectionReason)}
        />
        <Textarea
          label={t("bulkRejectNoteLabel")}
          rows={3}
          maxLength={2000}
          value={note}
          placeholder={t("bulkRejectNotePlaceholder")}
          help={t("bulkRejectNoteHelp")}
          onChange={(e) => onNoteChange(e.target.value)}
        />
      </div>
    </Modal>
  );
}
