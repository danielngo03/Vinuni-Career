"use client";

import { useTranslations } from "next-intl";
import { Eye } from "lucide-react";
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
      className="rounded-lg p-3.5"
      style={{ background: "var(--content-warning-soft)" }}
    >
      <p className="flex items-start gap-2 type-small font-semibold text-foreground">
        <Eye
          aria-hidden
          className="mt-0.5 size-4 shrink-0"
          strokeWidth={1.8}
          style={{ color: "var(--content-warning)" }}
        />
        {t("revealBlockedTitle")}
      </p>
      <p className="mt-1 type-caption text-muted-foreground">{t("revealBlockedBody")}</p>
      {pending ? (
        <p className="mt-2 type-caption font-medium" style={{ color: "var(--content-warning)" }}>
          {t("revealBlockedPending")}
        </p>
      ) : (
        <Button variant="secondary" size="sm" className="mt-2.5" onClick={onRequestReveal}>
          <Eye aria-hidden className="size-4" strokeWidth={1.8} />
          {t("revealBlockedCta")}
        </Button>
      )}
    </div>
  );
}
