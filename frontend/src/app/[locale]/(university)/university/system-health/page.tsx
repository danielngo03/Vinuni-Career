import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { SystemHealthScreen } from "@/components/admin/system-health-screen";

/**
 * System health page (`/university/system-health`).
 * Superadmin-only. Renders near-realtime scheduled jobs, queue depth, and
 * service readiness panels. `SuperadminGuard` redirects non-superadmin staff
 * to `/university/dashboard`.
 */
export default function SystemHealthPage() {
  return (
    <SuperadminGuard>
      <SystemHealthScreen />
    </SuperadminGuard>
  );
}
