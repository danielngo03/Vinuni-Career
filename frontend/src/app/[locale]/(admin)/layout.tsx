import { AdminGuard } from "@/components/layout/admin-guard";
import { AdminShell } from "@/components/layout/admin-shell";

/**
 * Layout for the superadmin `(admin)` route group.
 *
 * - `AdminGuard` redirects non-superadmin users (or guests) to `/`.
 * - `AdminShell` renders the admin sidebar (ADMIN_NAV_GROUPS) and topbar.
 *
 * Locale and message loading are handled by the parent `[locale]/layout.tsx`
 * (same as all other route groups — no per-group override needed).
 */
export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AdminGuard>
      <AdminShell>{children}</AdminShell>
    </AdminGuard>
  );
}
