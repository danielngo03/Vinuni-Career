import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { AiSettingsScreen } from "@/components/ai-settings/ai-settings-screen";

/**
 * AI Settings page (`/university/ai-settings`).
 * Superadmin-only. Exposes the real provider/model registry (`AiProviderManager`),
 * alias governance, activation/rollout, budget, and the kill switch — none of
 * which may be shown to ordinary university staff (CLAUDE.md AI-leakage rule).
 * `SuperadminGuard` redirects non-superadmin staff to `/university/dashboard`;
 * backend RBAC remains the final authority on every admin AI endpoint.
 */
export default function UniversityAiSettingsPage() {
  return (
    <SuperadminGuard>
      <AiSettingsScreen />
    </SuperadminGuard>
  );
}
