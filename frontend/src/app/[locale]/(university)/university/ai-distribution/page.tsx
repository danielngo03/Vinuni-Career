import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { AiAllocationsScreen } from "@/components/admin/ai-allocations-screen";

/**
 * AI Energy Distribution page (`/university/ai-distribution`).
 * Superadmin-only. The platform superadmin distributes weekly AI energy down the
 * organization → department → user tree, and reviews staff capacity requests.
 * `SuperadminGuard` redirects non-superadmin staff to `/university/dashboard`.
 */
export default function AiDistributionPage() {
  return (
    <SuperadminGuard>
      <AiAllocationsScreen />
    </SuperadminGuard>
  );
}
