import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { LogsExplorerScreen } from "@/components/admin/logs-explorer-screen";

/**
 * Unified Logs & Activity page (`/university/logs`).
 * Superadmin-only. Composes system audit log and AI event log into a single
 * explorer with source selector (Recent / System / AI) and per-source filters.
 * `SuperadminGuard` redirects non-superadmin staff to `/university/dashboard`.
 */
export default function LogsPage() {
  return (
    <SuperadminGuard>
      <LogsExplorerScreen />
    </SuperadminGuard>
  );
}
