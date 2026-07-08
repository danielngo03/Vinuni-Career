"use client";

import { useTranslations } from "next-intl";
import { Prohibit, X } from "@phosphor-icons/react";
import { Button } from "@/components/ui";

export function BulkActionBar({
  count,
  reviewPending,
  rejectPending,
  onReview,
  onReject,
  onClear,
  t,
}: {
  count: number;
  reviewPending: boolean;
  rejectPending: boolean;
  onReview: () => void;
  onReject: () => void;
  onClear: () => void;
  t: ReturnType<typeof useTranslations>;
}) {
  const busy = reviewPending || rejectPending;
  return (
    <div
      role="toolbar"
      aria-label={t("bulkToolbarAria")}
      className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 flex items-center gap-2.5 rounded-2xl border border-[var(--border-default)] bg-[var(--brand-primary)] px-4 py-2.5 shadow-[0_8px_32px_rgba(11,34,57,0.22)] "
    >
      <span className="text-sm font-semibold text-white">
        {t("bulkCount", { count })}
      </span>
      <div className="h-4 w-px bg-white/30" aria-hidden />
      <Button
        variant="secondary"
        size="sm"
        loading={reviewPending}
        disabled={busy}
        onClick={onReview}
        className="!border-[var(--border-default)] !bg-white/20 !text-white hover:!bg-white/30"
      >
        {t("bulkReviewCta")}
      </Button>
      <Button
        variant="danger"
        size="sm"
        loading={rejectPending}
        disabled={busy}
        onClick={onReject}
      >
        <Prohibit aria-hidden weight="bold" className="size-4" />
        {t("bulkRejectCta")}
      </Button>
      <button
        type="button"
        aria-label={t("bulkClearAria")}
        disabled={busy}
        onClick={onClear}
        className="ml-1 inline-flex items-center rounded-lg p-1 text-white/70 outline-none hover:text-white focus-visible:ring-2 focus-visible:ring-white/40 disabled:opacity-50"
      >
        <X aria-hidden weight="bold" className="size-4" />
      </button>
    </div>
  );
}
