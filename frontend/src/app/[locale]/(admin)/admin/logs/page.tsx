import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { LogsExplorerScreen } from "@/components/admin/logs-explorer-screen";

/**
 * Unified Logs & Activity (`/admin/logs`). Superadmin-only explorer composing
 * system audit and AI event logs. Guarded at the shell and per page.
 */
export default function AdminLogsPage() {
  return (
    <SuperadminGuard>
      <LogsExplorerScreen />
    </SuperadminGuard>
  );
}
