"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { CheckCircle } from "@phosphor-icons/react";
import { usePathname } from "@/i18n/navigation";
import { Button, Modal, Textarea, useToast } from "@/components/ui";
import { feedbackApi } from "@/lib/api";
import { cn } from "@/lib/utils";

type Category = "bug" | "suggestion" | "praise" | "other";

const CATEGORIES: Category[] = ["bug", "suggestion", "praise", "other"];

const CATEGORY_KEYS = {
  bug: "categoryBug",
  suggestion: "categorySuggestion",
  praise: "categoryPraise",
  other: "categoryOther",
} as const;

const CATEGORY_COLORS: Record<Category, string> = {
  bug: "bg-[var(--rose-50)] border-[var(--rose-200)] text-[var(--rose-700)] data-[selected]:bg-[var(--rose-100)] data-[selected]:border-[var(--rose-400)]",
  suggestion: "bg-[var(--blue-50)] border-[var(--blue-200)] text-[var(--blue-700)] data-[selected]:bg-[var(--blue-100)] data-[selected]:border-[var(--blue-400)]",
  praise: "bg-[var(--emerald-50)] border-[var(--emerald-200)] text-[var(--emerald-700)] data-[selected]:bg-[var(--emerald-100)] data-[selected]:border-[var(--emerald-400)]",
  other: "bg-[var(--gray-50)] border-[var(--gray-200)] text-[var(--text-secondary)] data-[selected]:bg-[var(--gray-100)] data-[selected]:border-[var(--gray-400)]",
};

interface FeedbackModalProps {
  open: boolean;
  onClose: () => void;
}

export function FeedbackModal({ open, onClose }: FeedbackModalProps) {
  const t = useTranslations("feedback");
  const toast = useToast();
  const pathname = usePathname();

  const [category, setCategory] = useState<Category>("suggestion");
  const [message, setMessage] = useState("");
  const [done, setDone] = useState(false);

  function handleClose() {
    onClose();
    // Reset after close animation
    setTimeout(() => {
      setCategory("suggestion");
      setMessage("");
      setDone(false);
    }, 300);
  }

  const mutation = useMutation({
    mutationFn: () =>
      feedbackApi.submit({
        category,
        message: message.trim(),
        page_url: pathname,
      }),
    onSuccess: () => {
      setDone(true);
    },
    onError: () => {
      toast.show({ tone: "error", title: t("errorGeneric") });
    },
  });

  const canSubmit = message.trim().length >= 3 && !mutation.isPending;

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title={t("title")}
      description={t("subtitle")}
    >
      {done ? (
        <div className="mt-6 flex flex-col items-center gap-3 py-4 text-center">
          <span className="flex size-14 items-center justify-center rounded-full icon-chip-success shadow-[0_4px_20px_rgba(16,185,129,0.30)]">
            <CheckCircle weight="fill" className="size-8 text-white" aria-hidden />
          </span>
          <p className="text-base font-semibold text-[var(--text-primary)]">
            {t("successTitle")}
          </p>
          <p className="text-sm text-[var(--text-secondary)]">{t("successBody")}</p>
          <Button className="mt-2" onClick={handleClose}>
            {t("cancel")}
          </Button>
        </div>
      ) : (
        <div className="mt-4 space-y-4">
          {/* Category chips */}
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
              {t("categoryLabel")}
            </p>
            <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={t("categoryLabel")}>
              {CATEGORIES.map((cat) => (
                <button
                  key={cat}
                  type="button"
                  role="radio"
                  aria-checked={category === cat}
                  data-selected={category === cat ? "" : undefined}
                  onClick={() => setCategory(cat)}
                  className={cn(
                    "rounded-full border px-3.5 py-1.5 text-xs font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
                    CATEGORY_COLORS[cat],
                  )}
                >
                  {t(CATEGORY_KEYS[cat])}
                </button>
              ))}
            </div>
          </div>

          {/* Message */}
          <div>
            <Textarea
              label={t("messageLabel")}
              placeholder={t("messagePlaceholder")}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={4}
              maxLength={1000}
              help={t("messageHint", { count: message.length })}
            />
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={handleClose} disabled={mutation.isPending}>
              {t("cancel")}
            </Button>
            <Button
              variant="primary"
              onClick={() => mutation.mutate()}
              disabled={!canSubmit}
            >
              {mutation.isPending ? t("submitting") : t("submit")}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
