"use client";

import { useTranslations } from "next-intl";
import { Button, Modal } from "@/components/ui";

/** Reusable destructive-action confirm dialog (no native confirm()). */
export function ConfirmDeleteModal({
  open,
  onClose,
  onConfirm,
  title,
  description,
  loading,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description: string;
  loading?: boolean;
}) {
  const tc = useTranslations("common");
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      description={description}
      size="sm"
      closeLabel={tc("close")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            {tc("cancel")}
          </Button>
          <Button variant="danger" loading={loading} onClick={onConfirm}>
            {tc("delete")}
          </Button>
        </>
      }
    >
      <p className="text-sm text-[var(--text-secondary)]">{description}</p>
    </Modal>
  );
}
