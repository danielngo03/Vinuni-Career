"use client";

import { useEffect } from "react";
import { useRouter } from "@/i18n/navigation";
import { useAuthStore } from "@/stores/auth-store";

/**
 * Guards a subtree so it is only rendered when the current authenticated user
 * has `isSuperadmin === true`. Any other state (loading, guest, non-superadmin)
 * redirects to `/university/dashboard` or shows nothing until auth resolves.
 *
 * Used as a per-page wrapper for the four superadmin-only pages that live
 * inside the university route group (`/university/platform-overview`,
 * `/university/ai-operations`, `/university/audit-log`,
 * `/university/system-health`). The university layout wraps all staff and
 * cannot enforce superadmin access by itself.
 *
 * SECURITY NOTE: this is a UX guard only — backend RBAC must enforce the same
 * permission on every admin API endpoint.
 */
export function SuperadminGuard({ children }: { children: React.ReactNode }) {
  const status = useAuthStore((s) => s.status);
  const isSuperadmin = useAuthStore((s) => s.user?.isSuperadmin ?? false);
  const router = useRouter();

  useEffect(() => {
    if (status === "unknown") return; // still hydrating — wait
    if (status === "guest" || !isSuperadmin) {
      router.replace("/university/dashboard");
    }
  }, [status, isSuperadmin, router]);

  // While auth is resolving or the user is not a superadmin, render nothing
  // (no flash of forbidden content).
  if (status === "unknown" || status === "guest" || !isSuperadmin) {
    return null;
  }

  return <>{children}</>;
}
