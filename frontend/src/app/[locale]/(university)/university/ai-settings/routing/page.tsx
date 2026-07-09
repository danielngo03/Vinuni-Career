import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { RoutingCanvasScreen } from "@/components/ai-settings/routing-canvas-screen";

/**
 * AI routing map page (`/university/ai-settings/routing`).
 * Superadmin-only: the routing canvas configures the real provider/model
 * registry, which is platform-superadmin territory. `SuperadminGuard`
 * redirects ordinary university staff to `/university/dashboard`.
 */
export default function UniversityAiRoutingCanvasPage() {
  return (
    <SuperadminGuard>
      <RoutingCanvasScreen />
    </SuperadminGuard>
  );
}
