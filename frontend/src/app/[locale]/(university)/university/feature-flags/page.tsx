import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { FeatureFlagsScreen } from "@/components/admin/feature-flags-screen";

/**
 * Feature Flags page (`/university/feature-flags`).
 * Superadmin-only. Provides a flag CRUD interface and read-only permission
 * catalog matrix.
 * `SuperadminGuard` redirects non-superadmin staff to `/university/dashboard`.
 */
export default function FeatureFlagsPage() {
  return (
    <SuperadminGuard>
      <FeatureFlagsScreen />
    </SuperadminGuard>
  );
}
