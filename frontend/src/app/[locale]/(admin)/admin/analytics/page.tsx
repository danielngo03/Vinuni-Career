import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { AnalyticsScreen } from "@/components/admin/analytics-screen";

/**
 * Platform Analytics (`/admin/analytics`). Superadmin-only KPIs, recruitment
 * funnel, and growth trends. Guarded at the shell and per page.
 */
export default function AdminAnalyticsPage() {
  return (
    <SuperadminGuard>
      <AnalyticsScreen />
    </SuperadminGuard>
  );
}
