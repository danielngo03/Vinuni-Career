import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { PlatformOverviewScreen } from "@/components/admin/platform-overview-screen";

/**
 * Platform overview (`/admin/platform-overview`). Superadmin-only cross-domain
 * health snapshot. Guarded at the shell and per page.
 */
export default function AdminPlatformOverviewPage() {
  return (
    <SuperadminGuard>
      <PlatformOverviewScreen />
    </SuperadminGuard>
  );
}
