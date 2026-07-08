"use client";

import { useTranslations } from "next-intl";
import { UserFocus } from "@phosphor-icons/react";
import { Button } from "@/components/ui";

export function RevealBlocked({
  pending,
  onRequestReveal,
}: {
  pending: boolean;
  onRequestReveal: () => void;
}) {
  const t = useTranslations("interviews");
  return (
    <div
      role="status"
      className="rounded-xl border border-[var(--amber-600)]/40 bg-[var(--amber-100)] p-3.5"
    >
      <p className="flex items-start gap-2 text-sm font-semibold text-[var(--text-primary)]">
        <UserFocus
          aria-hidden
          weight="duotone"
          className="mt-0.5 size-4 shrink-0 text-[var(--amber-700)]"
        />
        {t("revealBlockedTitle")}
      </p>
      <p className="mt-1 text-xs text-[var(--text-secondary)]">
        {t("revealBlockedBody")}
      </p>
      {pending ? (
        <p className="mt-2 text-xs font-medium text-[var(--amber-700)]">
          {t("revealBlockedPending")}
        </p>
      ) : (
        <Button
          variant="secondary"
          size="sm"
          className="mt-2.5"
          onClick={onRequestReveal}
        >
          <UserFocus aria-hidden weight="bold" className="size-4" />
          {t("revealBlockedCta")}
        </Button>
      )}
    </div>
  );
}
