import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { AlertsScreen } from "@/components/admin/alerts-screen";

/**
 * Alerts & Incidents page (`/university/alerts`).
 * Superadmin-only. Provides incident management and alert rule CRUD.
 * `SuperadminGuard` redirects non-superadmin staff to `/university/dashboard`.
 */
export default function AlertsPage() {
  return (
    <SuperadminGuard>
      <AlertsScreen />
    </SuperadminGuard>
  );
}
