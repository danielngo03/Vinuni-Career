"use client";

import { useEffect } from "react";
import { useRouter } from "@/i18n/navigation";
import { useAuthStore } from "@/stores/auth-store";

/**
 * Guards a subtree so it is only rendered when the current authenticated user
 * has `isSuperadmin === true`. Any other state (loading, guest, non-superadmin)
 * redirects to `/` or shows nothing until the auth state resolves.
 *
 * SECURITY NOTE: this is a UX guard only — backend RBAC must enforce the same
 * permission on every admin API endpoint.
 */
export function AdminGuard({ children }: { children: React.ReactNode }) {
  const status = useAuthStore((s) => s.status);
  const isSuperadmin = useAuthStore((s) => s.user?.isSuperadmin ?? false);
  const router = useRouter();

  useEffect(() => {
    if (status === "unknown") return; // still hydrating — wait
    if (status === "guest" || !isSuperadmin) {
      router.replace("/");
    }
  }, [status, isSuperadmin, router]);

  // While auth is resolving or the user is not a superadmin, render nothing
  // (no flash of forbidden content).
  if (status === "unknown" || status === "guest" || !isSuperadmin) {
    return null;
  }

  return <>{children}</>;
}
