import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { AiAllocationsScreen } from "@/components/admin/ai-allocations-screen";

/**
 * AI Energy Distribution (`/admin/ai-distribution`). The superadmin distributes
 * weekly AI energy down the organization → department → user tree and reviews
 * staff capacity requests. Guarded at the shell and per page.
 */
export default function AdminAiDistributionPage() {
  return (
    <SuperadminGuard>
      <AiAllocationsScreen />
    </SuperadminGuard>
  );
}
