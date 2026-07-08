import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { RoutingCanvasScreen } from "@/components/ai-settings/routing-canvas-screen";

/**
 * AI routing canvas (`/university/ai-settings/routing`).
 * Superadmin-only — the routing canvas exposes provider/model routing internals
 * (aliases, model families, failover order). Ordinary staff never reach it: the
 * link into this page in the AI settings screen is also superadmin-gated.
 * `SuperadminGuard` redirects non-superadmin staff to `/university/dashboard`.
 */
export default function UniversityAiRoutingCanvasPage() {
  return (
    <SuperadminGuard>
      <RoutingCanvasScreen />
    </SuperadminGuard>
  );
}
