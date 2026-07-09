"use client";

import { useTranslations } from "next-intl";
import { Button, Modal, Textarea } from "@/components/ui";

export function RevealModal({
  open,
  onClose,
  reason,
  onReasonChange,
  reasonValid,
  minReason,
  loading,
  onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  reason: string;
  onReasonChange: (v: string) => void;
  reasonValid: boolean;
  minReason: number;
  loading: boolean;
  onSubmit: () => void;
}) {
  const t = useTranslations("candidates");
  const tc = useTranslations("common");

  return (
    <Modal
      open={open}
      onClose={loading ? () => {} : onClose}
      title={t("revealTitle")}
      description={t("revealDescription")}
      size="sm"
      closeLabel={tc("close")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            {tc("cancel")}
          </Button>
          <Button
            variant="primary"
            loading={loading}
            disabled={!reasonValid || loading}
            onClick={onSubmit}
          >
            {t("sendRequest")}
          </Button>
        </>
      }
    >
      <Textarea
        label={t("revealReasonLabel")}
        required
        rows={4}
        minLength={minReason}
        maxLength={500}
        value={reason}
        placeholder={t("revealReasonPlaceholder")}
        help={t("revealReasonHelp", { min: minReason, count: reason.trim().length })}
        onChange={(e) => onReasonChange(e.target.value)}
      />
    </Modal>
  );
}
