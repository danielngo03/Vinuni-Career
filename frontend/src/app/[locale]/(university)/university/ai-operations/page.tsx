import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { AiOperationsOverviewScreen } from "@/components/admin/ai-operations-overview-screen";

/**
 * AI Operations page (`/university/ai-operations`).
 * Superadmin-only. Renders the AI spend / reliability / volume / traces tabs.
 * `SuperadminGuard` redirects non-superadmin staff to `/university/dashboard`.
 */
export default function AiOperationsPage() {
  return (
    <SuperadminGuard>
      <AiOperationsOverviewScreen />
    </SuperadminGuard>
  );
}
