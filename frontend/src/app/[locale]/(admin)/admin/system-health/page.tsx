import { SystemHealthScreen } from "@/components/admin/system-health-screen";

/**
 * Platform system health page (`/admin/system-health`).
 * Superadmin-only. Renders near-realtime scheduled jobs, queue depth, and
 * service readiness panels. Auth gate is enforced in the (admin) layout.
 */
export default function SystemHealthPage() {
  return <SystemHealthScreen />;
}
