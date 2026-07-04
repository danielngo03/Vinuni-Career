"use client";

import { Button, Input, Modal } from "@/components/ui";
import type { Subscription } from "@/lib/api";
import { LabeledTextarea } from "./form-fields";

export function MarkPaidModal({
  open,
  selected,
  paymentRef,
  textError,
  loading,
  t,
  tc,
  onClose,
  onPaymentRefChange,
  onSubmit,
}: {
  open: boolean;
  selected: Subscription | null;
  paymentRef: string;
  textError: string | null;
  loading: boolean;
  t: ReturnType<typeof import("next-intl").useTranslations>;
  tc: (key: string) => string;
  onClose: () => void;
  onPaymentRefChange: (v: string) => void;
  onSubmit: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t("markPaidTitle")}
      description={t("markPaidBody", { plan: selected?.plan?.name ?? "" })}
      size="sm"
      closeLabel={tc("close")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button variant="primary" loading={loading} onClick={onSubmit}>
            {t("markPaidConfirm")}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <p className="text-sm text-[var(--text-secondary)]">{t("markPaidNote")}</p>
        <Input
          id="billing-payment-ref"
          label={t("paymentRefLabel")}
          required
          value={paymentRef}
          error={textError ?? undefined}
          onChange={(e) => onPaymentRefChange(e.target.value)}
          placeholder={t("paymentRefPlaceholder")}
          help={t("paymentRefHint")}
        />
      </div>
    </Modal>
  );
}

export function CancelSubscriptionModal({
  open,
  selected,
  reason,
  loading,
  t,
  tc,
  onClose,
  onReasonChange,
  onSubmit,
}: {
  open: boolean;
  selected: Subscription | null;
  reason: string;
  loading: boolean;
  t: ReturnType<typeof import("next-intl").useTranslations>;
  tc: (key: string) => string;
  onClose: () => void;
  onReasonChange: (v: string) => void;
  onSubmit: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t("cancelTitle")}
      description={t("cancelBody", { plan: selected?.plan?.name ?? "" })}
      size="sm"
      closeLabel={tc("close")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {tc("back")}
          </Button>
          <Button variant="danger" loading={loading} onClick={onSubmit}>
            {t("cancelConfirm")}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <p className="text-sm text-[var(--text-secondary)]">{t("cancelNote")}</p>
        <LabeledTextarea
          id="billing-cancel-reason"
          label={t("cancelReasonLabel")}
          value={reason}
          onChange={onReasonChange}
          hint={t("cancelReasonHint")}
        />
      </div>
    </Modal>
  );
}
