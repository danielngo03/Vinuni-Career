import { MyAiCapacitySection } from "@/components/ai-governance/my-ai-capacity-section";

/**
 * AI Governance (`/university/ai-governance`). Staff-facing AI energy view:
 * the caller's weekly AI energy status plus the capacity-request workflow
 * (distribution, not billing — a superadmin approves and raises the ceiling).
 * Superadmins see an "unlimited" state with nothing to request. Energy is shown
 * as opaque credits/percentages only — never tokens, cost, provider, or model.
 */
export default function UniversityAiGovernancePage() {
  return <MyAiCapacitySection />;
}
