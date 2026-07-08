import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { AlertsScreen } from "@/components/admin/alerts-screen";

/**
 * Alerts & Incidents (`/admin/alerts`). Superadmin-only incident management and
 * alert rule CRUD. Guarded at the shell and per page.
 */
export default function AdminAlertsPage() {
  return (
    <SuperadminGuard>
      <AlertsScreen />
    </SuperadminGuard>
  );
}
