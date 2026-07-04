"use client";

import { CurrencyCircleDollar, Prohibit } from "@phosphor-icons/react";
import { Button, Modal, StatusBadge } from "@/components/ui";
import { useBillingLabels, SUBSCRIPTION_STATUS_TONE } from "@/lib/billing/labels";
import { formatVnd, formatWindow } from "@/lib/billing/format";
import type { Subscription } from "@/lib/api";
import { Field } from "./form-fields";

export function SubscriptionReviewModal({
  selected,
  open,
  locale,
  t,
  tc,
  canMarkPaid,
  canCancel,
  onClose,
  onOpenMarkPaid,
  onOpenCancel,
}: {
  selected: Subscription | null;
  open: boolean;
  locale: string;
  t: ReturnType<typeof import("next-intl").useTranslations>;
  tc: (key: string) => string;
  canMarkPaid: boolean;
  canCancel: boolean;
  onClose: () => void;
  onOpenMarkPaid: () => void;
  onOpenCancel: () => void;
}) {
  const labels = useBillingLabels();

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t("reviewTitle")}
      size="md"
      closeLabel={tc("close")}
    >
      {selected && (
        <div className="space-y-4">
          <div>
            <h3 className="text-base font-bold text-[var(--text-primary)]">
              {selected.plan?.name ?? "—"}
            </h3>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <StatusBadge tone={SUBSCRIPTION_STATUS_TONE[selected.status] ?? "info"}>
                {labels.status(selected.status, selected.status_label)}
              </StatusBadge>
              {selected.plan && (
                <StatusBadge tone="info">
                  {labels.audience(selected.plan.audience, selected.plan.audience_label)}
                </StatusBadge>
              )}
            </div>
          </div>

          {selected.principal_id && (
            <Field label={t("fieldPrincipal")}>
              <span className="font-mono text-xs">{selected.principal_id}</span>
            </Field>
          )}
          <Field label={t("colPrice")}>
            {formatVnd(selected.price_amount, selected.currency, locale)}{" "}
            <span
              className={
                selected.is_paid
                  ? "text-[var(--teal-600)]"
                  : "text-[var(--amber-700)]"
              }
            >
              ({selected.is_paid ? t("paid") : t("unpaid")})
            </span>
          </Field>
          <Field label={t("colWindow")}>
            {formatWindow(selected.start_at, selected.end_at, locale)}
          </Field>
          {selected.payment_reference && (
            <Field label={t("fieldPaymentRef")}>
              <span className="font-mono text-xs">{selected.payment_reference}</span>
            </Field>
          )}
          {selected.cancel_reason && (
            <Field label={t("fieldCancelReason")}>{selected.cancel_reason}</Field>
          )}

          <div className="flex flex-col gap-2 pt-2">
            {canMarkPaid && (
              <Button variant="primary" fullWidth onClick={onOpenMarkPaid}>
                <CurrencyCircleDollar aria-hidden weight="bold" className="size-4" />
                {t("markPaid")}
              </Button>
            )}
            {canCancel && (
              <Button variant="danger" fullWidth onClick={onOpenCancel}>
                <Prohibit aria-hidden weight="bold" className="size-4" />
                {t("cancel")}
              </Button>
            )}
            {!canMarkPaid && !canCancel && (
              <p className="rounded-lg border border-white/50 bg-white/70 px-3 py-2 text-sm text-[var(--text-secondary)] backdrop-blur-sm">
                {t("noActions")}
              </p>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}
