"use client";

import { useTranslations } from "next-intl";
import { BookmarkSimple } from "@phosphor-icons/react";
import { useRouter } from "@/i18n/navigation";
import { useAuthStore } from "@/stores/auth-store";
import { useUiStore } from "@/stores/ui-store";
import { cn } from "@/lib/utils";

const SAVED_ROUTE = "/student/saved";

/**
 * Saved/bookmark affordance for the public header and mobile drawer. There is
 * no saved-jobs backend yet, so this is an honest login-intent entry: guests
 * open the intent-preserving login modal; authenticated users land on the
 * Saved route, which renders an honest under-construction state. No fabricated
 * saved data (CLAUDE.md: do not fake backends).
 */
export function SavedButton({ variant = "icon" }: { variant?: "icon" | "row" }) {
  const tNav = useTranslations("nav");
  const tm = useTranslations("marketplace");
  const router = useRouter();
  const status = useAuthStore((s) => s.status);
  const openLoginModal = useUiStore((s) => s.openLoginModal);

  function handleClick() {
    if (status === "authenticated") {
      router.push(SAVED_ROUTE);
      return;
    }
    openLoginModal({ label: tm("savedIntent"), returnTo: SAVED_ROUTE });
  }

  if (variant === "row") {
    return (
      <button
        type="button"
        onClick={handleClick}
        className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-medium text-[var(--text-secondary)] outline-none hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
      >
        <BookmarkSimple aria-hidden weight="duotone" className="size-5" />
        {tNav("saved")}
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      aria-label={tNav("saved")}
      title={tNav("saved")}
      className={cn(
        "inline-flex size-9 items-center justify-center rounded-lg text-[var(--text-secondary)] outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
      )}
    >
      <BookmarkSimple aria-hidden weight="duotone" className="size-5" />
    </button>
  );
}
