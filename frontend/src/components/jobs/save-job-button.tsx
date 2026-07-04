"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Heart } from "@phosphor-icons/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useToast } from "@/components/ui";
import { useUiStore } from "@/stores/ui-store";
import { useAuthStore } from "@/stores/auth-store";
import { jobsApi } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Heart save/favourite affordance (icon semantics spec §2: Heart).
 *
 * - Guests → intent-preserving login modal.
 * - Authenticated students → optimistic toggle that persists to the backend.
 * - Controlled via `initialSaved` prop so the job detail/card can seed the state
 *   from the server's `is_saved` field without an extra query.
 */
export function SaveJobButton({
  jobId,
  returnTo,
  initialSaved = false,
  size = "md",
  className,
}: {
  jobId: string;
  /** Where to resume after login (e.g. the job detail). */
  returnTo?: string;
  /** Seed from the server's `is_saved` field. */
  initialSaved?: boolean;
  size?: "sm" | "md";
  className?: string;
}) {
  const t = useTranslations("jobs");
  const toast = useToast();
  const status = useAuthStore((s) => s.status);
  const persona = useAuthStore((s) => s.user?.persona);
  const openLoginModal = useUiStore((s) => s.openLoginModal);
  const qc = useQueryClient();
  const [saved, setSaved] = useState(initialSaved);
  const isAuthenticatedNonStudent =
    status === "authenticated" && persona !== "student";

  const saveMutation = useMutation({
    mutationFn: () => jobsApi.saveJob(jobId),
    onMutate: () => setSaved(true),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["jobs", "saved"] });
    },
    onError: () => {
      setSaved(false);
      toast.show({ tone: "error", title: t("saveError") });
    },
  });

  const unsaveMutation = useMutation({
    mutationFn: () => jobsApi.unsaveJob(jobId),
    onMutate: () => setSaved(false),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["jobs", "saved"] });
    },
    onError: () => {
      setSaved(true);
      toast.show({ tone: "error", title: t("saveError") });
    },
  });

  function handleClick(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();

    if (status !== "authenticated") {
      openLoginModal({
        label: t("saveIntent"),
        returnTo: returnTo ?? `/jobs/${jobId}`,
        payload: { intent: "save_job", jobId },
      });
      return;
    }

    if (isAuthenticatedNonStudent) return;

    if (saved) {
      unsaveMutation.mutate();
    } else {
      saveMutation.mutate();
    }
  }

  const pending = saveMutation.isPending || unsaveMutation.isPending;
  const box = size === "sm" ? "size-8" : "size-9";
  const icon = size === "sm" ? "size-4" : "size-[1.15rem]";

  if (isAuthenticatedNonStudent) return null;

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={pending}
      aria-label={saved ? t("unsaveJob") : t("saveJob")}
      aria-pressed={saved}
      title={saved ? t("unsaveJob") : t("saveJob")}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-lg border bg-[var(--glass-surface)] backdrop-blur outline-none transition-colors disabled:opacity-60",
        saved
          ? "border-[var(--brand-red)]/50 text-[var(--brand-red)] hover:bg-[var(--red-50)]"
          : "border-[var(--glass-border)] text-[var(--text-muted)] hover:border-[var(--brand-red)]/40 hover:bg-[var(--red-50)] hover:text-[var(--brand-red)]",
        "focus-visible:ring-2 focus-visible:ring-[var(--brand-red)]/40",
        box,
        className,
      )}
    >
      <Heart
        aria-hidden
        weight={saved ? "fill" : "duotone"}
        className={icon}
      />
    </button>
  );
}
