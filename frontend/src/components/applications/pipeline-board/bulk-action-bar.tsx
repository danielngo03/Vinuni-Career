"use client";

import { useTranslations } from "next-intl";
import { Ban, X } from "lucide-react";
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
      className="fixed bottom-6 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2.5 rounded-xl bg-foreground px-4 py-2.5 shadow-[var(--shadow-xl)]"
    >
      <span className="text-sm font-semibold text-[var(--surface-card)]">{t("bulkCount", { count })}</span>
      <div className="h-4 w-px bg-white/25" aria-hidden />
      <Button
        variant="secondary"
        size="sm"
        loading={reviewPending}
        disabled={busy}
        onClick={onReview}
        className="!border-white/20 !bg-white/15 !text-white hover:!bg-white/25"
      >
        {t("bulkReviewCta")}
      </Button>
      <Button variant="danger" size="sm" loading={rejectPending} disabled={busy} onClick={onReject}>
        <Ban aria-hidden className="size-4" strokeWidth={2} />
        {t("bulkRejectCta")}
      </Button>
      <button
        type="button"
        aria-label={t("bulkClearAria")}
        disabled={busy}
        onClick={onClear}
        className="ml-1 inline-flex items-center rounded-lg p-1 text-white/70 outline-none hover:text-white focus-visible:ring-2 focus-visible:ring-white/40 disabled:opacity-50"
      >
        <X aria-hidden className="size-4" strokeWidth={2} />
      </button>
    </div>
  );
}
