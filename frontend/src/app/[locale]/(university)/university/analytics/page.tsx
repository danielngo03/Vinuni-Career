import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { AnalyticsScreen } from "@/components/admin/analytics-screen";

/**
 * Platform Analytics page (`/university/analytics`).
 * Superadmin-only. Renders KPI tiles, recruitment funnel, and growth chart.
 * `SuperadminGuard` redirects non-superadmin staff to `/university/dashboard`.
 */
export default function AnalyticsPage() {
  return (
    <SuperadminGuard>
      <AnalyticsScreen />
    </SuperadminGuard>
  );
}
