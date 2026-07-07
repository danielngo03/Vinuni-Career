import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { AuditLogScreen } from "@/components/admin/audit-log-screen";

/**
 * Audit log page (`/university/audit-log`).
 * Superadmin-only. Renders the cursor-paginated audit log with filter bar and
 * CSV export. `SuperadminGuard` redirects non-superadmin staff to
 * `/university/dashboard`.
 */
export default function AuditLogPage() {
  return (
    <SuperadminGuard>
      <AuditLogScreen />
    </SuperadminGuard>
  );
}
