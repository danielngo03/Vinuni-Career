import { AuditLogScreen } from "@/components/admin/audit-log-screen";

/**
 * Platform audit log page (`/admin/audit-log`).
 * Superadmin-only. Renders the cursor-paginated audit log console with filter
 * bar, row→Sheet detail view, and CSV export.
 */
export default function AuditLogPage() {
  return <AuditLogScreen />;
}
