import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { AuditLogScreen } from "@/components/admin/audit-log-screen";

/**
 * Audit Log (`/admin/audit-log`). Superadmin-only cursor-paginated audit log
 * with filter bar and CSV export. Guarded at the shell and per page.
 */
export default function AdminAuditLogPage() {
  return (
    <SuperadminGuard>
      <AuditLogScreen />
    </SuperadminGuard>
  );
}
