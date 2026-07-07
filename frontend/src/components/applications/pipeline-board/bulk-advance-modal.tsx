"use client";

import { useTranslations } from "next-intl";
import { ArrowRight } from "@phosphor-icons/react";
import { Button, Modal } from "@/components/ui";

/**
 * Lightweight confirm for a bulk advance (BUSINESS_LOGIC §3.6). Advancing is
 * reversible (rollback), so this is a brief confirmation, not a heavy form. The
 * backend still gates each candidate — ineligible ones (missing scorecard /
 * below threshold) are reported back, never force-advanced.
 */
export function BulkAdvanceModal({
  open,
  count,
  loading,
  onClose,
  onSubmit,
  t,
}: {
  open: boolean;
  count: number;
  loading: boolean;
  onClose: () => void;
  onSubmit: () => void;
  t: ReturnType<typeof useTranslations>;
}) {
  const tc = useTranslations("common");
  return (
    <Modal
      open={open}
      onClose={loading ? () => {} : onClose}
      title={t("bulkAdvanceConfirmTitle")}
      description={t("bulkAdvanceConfirmBody", { count })}
      size="sm"
      closeLabel={tc("close")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            {tc("cancel")}
          </Button>
          <Button variant="primary" loading={loading} onClick={onSubmit}>
            <ArrowRight aria-hidden weight="bold" className="size-4" />
            {t("bulkAdvanceConfirmSubmit", { count })}
          </Button>
        </>
      }
    >
      <p className="text-sm text-[var(--text-secondary)]">
        {t("bulkAdvanceConfirmHint")}
      </p>
    </Modal>
  );
}
