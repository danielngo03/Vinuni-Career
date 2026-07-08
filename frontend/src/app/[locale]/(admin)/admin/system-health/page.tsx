import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { SystemHealthScreen } from "@/components/admin/system-health-screen";

/**
 * System Health (`/admin/system-health`). Superadmin-only near-realtime jobs,
 * queue depth, and service readiness. Guarded at the shell and per page.
 */
export default function AdminSystemHealthPage() {
  return (
    <SuperadminGuard>
      <SystemHealthScreen />
    </SuperadminGuard>
  );
}
