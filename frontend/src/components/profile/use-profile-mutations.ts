"use client";

import { useTranslations } from "next-intl";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, type StudentProfile } from "@/lib/api";
import { useToast } from "@/components/ui";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { useAuthStore } from "@/stores/auth-store";

export const PROFILE_QUERY_KEY = ["student", "profile"] as const;

/**
 * Shared mutation helpers for the profile editor. Centralizes:
 *  - writing the full profile into the query cache after a core/privacy save,
 *  - refetching after a child write (completion % + child versions change),
 *  - friendly optimistic-conflict recovery (toast + reload), so a stale
 *    `expected_version` never throws a raw error at the user.
 */
export function useProfileMutations() {
  const qc = useQueryClient();
  const toast = useToast();
  const getMessage = useApiErrorMessage();
  const tc = useTranslations("common");
  const t = useTranslations("profile");
  const authUser = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);

  const setProfile = (profile: StudentProfile) => {
    qc.setQueryData(PROFILE_QUERY_KEY, profile);
    // Sync avatar_url to auth store so topbar/sidebar reflect the change immediately.
    if (authUser && "avatar_url" in profile) {
      setUser({ ...authUser, avatarUrl: profile.avatar_url ?? null });
    }
  };

  const reloadProfile = () => {
    void qc.invalidateQueries({ queryKey: PROFILE_QUERY_KEY });
  };

  /** Returns true if the error was a handled optimistic conflict. */
  const handleError = (error: unknown): boolean => {
    if (error instanceof ApiError && error.code === "CONFLICT") {
      toast.show({ tone: "warning", title: tc("conflictReload") });
      reloadProfile();
      return true;
    }
    toast.show({ tone: "error", title: getMessage(error) });
    return false;
  };

  const notifySaved = () => {
    toast.show({ tone: "success", title: t("saved") });
  };

  return { setProfile, reloadProfile, handleError, notifySaved };
}
