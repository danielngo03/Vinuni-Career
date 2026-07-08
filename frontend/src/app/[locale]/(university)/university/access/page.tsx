import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { UsersAccessScreen } from "@/components/admin/users-access-screen";

/**
 * Users & Access page (`/university/access`).
 * Superadmin-only. Provides platform-wide user management, 360-degree user
 * view, superadmin grant/revoke, suspend/unsuspend, and session management.
 * `SuperadminGuard` redirects non-superadmin staff to `/university/dashboard`.
 */
export default function UsersAccessPage() {
  return (
    <SuperadminGuard>
      <UsersAccessScreen />
    </SuperadminGuard>
  );
}
