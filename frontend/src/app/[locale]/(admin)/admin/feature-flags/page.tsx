import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { FeatureFlagsScreen } from "@/components/admin/feature-flags-screen";

/**
 * Feature Flags (`/admin/feature-flags`). Superadmin-only flag CRUD and
 * read-only permission catalog matrix. Guarded at the shell and per page.
 */
export default function AdminFeatureFlagsPage() {
  return (
    <SuperadminGuard>
      <FeatureFlagsScreen />
    </SuperadminGuard>
  );
}
