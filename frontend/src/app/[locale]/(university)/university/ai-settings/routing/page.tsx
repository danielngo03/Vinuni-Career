import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { RoutingCanvasScreen } from "@/components/ai-settings/routing-canvas-screen";

/**
 * AI routing canvas (`/university/ai-settings/routing`).
 * Superadmin-only: maps masked aliases to concrete provider/model routes, which
 * are part of the real registry and must never reach ordinary staff.
 */
export default function UniversityAiRoutingCanvasPage() {
  return (
    <SuperadminGuard>
      <RoutingCanvasScreen />
    </SuperadminGuard>
  );
}
