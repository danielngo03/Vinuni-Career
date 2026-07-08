import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { AiOperationsOverviewScreen } from "@/components/admin/ai-operations-overview-screen";

/**
 * AI Operations (`/admin/ai-operations`). Superadmin-only spend / reliability /
 * volume / traces. Guarded at the shell and per page.
 */
export default function AdminAiOperationsPage() {
  return (
    <SuperadminGuard>
      <AiOperationsOverviewScreen />
    </SuperadminGuard>
  );
}
