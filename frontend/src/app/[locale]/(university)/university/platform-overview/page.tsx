import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { PlatformOverviewScreen } from "@/components/admin/platform-overview-screen";

/**
 * Platform overview page (`/university/platform-overview`).
 * Superadmin-only. Renders the cross-domain health snapshot.
 * `SuperadminGuard` redirects non-superadmin staff to `/university/dashboard`.
 */
export default function PlatformOverviewPage() {
  return (
    <SuperadminGuard>
      <PlatformOverviewScreen />
    </SuperadminGuard>
  );
}
