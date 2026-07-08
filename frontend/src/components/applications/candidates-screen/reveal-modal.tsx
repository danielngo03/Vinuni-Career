"use client";

import { useTranslations } from "next-intl";
import { Button, Sheet } from "@/components/ui";

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
    <Sheet open={open} onClose={onClose} title={t("revealTitle")} closeLabel={tc("close")}>
      <div className="space-y-4">
        <p className="text-sm text-[var(--text-secondary)]">
          {t("revealDescription")}
        </p>
        <div>
          <label
            htmlFor="reveal-reason"
            className="mb-1.5 block text-sm font-semibold text-[var(--text-primary)]"
          >
            {t("revealReasonLabel")}
          </label>
          <textarea
            id="reveal-reason"
            value={reason}
            onChange={(e) => onReasonChange(e.target.value)}
            rows={4}
            minLength={minReason}
            maxLength={500}
            placeholder={t("revealReasonPlaceholder")}
            aria-describedby="reveal-reason-help"
            className="w-full rounded-xl border border-white/60 bg-white/80 px-3.5 py-2.5 text-sm text-[var(--text-primary)] outline-none backdrop-blur-sm transition-colors placeholder:text-[var(--text-muted)] focus:border-[var(--brand-primary)]/50 focus:bg-white/95 focus:ring-2 focus:ring-[var(--brand-primary)]/30"
          />
          <p
            id="reveal-reason-help"
            className={
              reasonValid
                ? "mt-1 text-xs text-[var(--text-muted)]"
                : "mt-1 text-xs text-[var(--text-secondary)]"
            }
          >
            {t("revealReasonHelp", { min: minReason, count: reason.trim().length })}
          </p>
        </div>
        <div className="flex justify-end gap-2">
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
        </div>
      </div>
    </Sheet>
  );
}
