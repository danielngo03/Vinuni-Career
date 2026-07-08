import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { UsersAccessScreen } from "@/components/admin/users-access-screen";

/**
 * Users & Access (`/admin/access`). Superadmin-only platform-wide user
 * management, 360-degree user view, grant/revoke, suspend, and session
 * management. Guarded at the shell and per page.
 */
export default function AdminUsersAccessPage() {
  return (
    <SuperadminGuard>
      <UsersAccessScreen />
    </SuperadminGuard>
  );
}
