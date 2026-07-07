import { AiOperationsOverviewScreen } from "@/components/admin/ai-operations-overview-screen";

/**
 * AI Operations overview page (`/admin/ai-operations`).
 *
 * Renders the Tabs shell: Overview (this slice), plus placeholder tab triggers
 * for Traces / Models & Pricing / Settings (Task 15 fills those panels).
 *
 * The screen is a client component that fetches four independent React Query
 * keys (overview, spend, reliability, volume) with visibility-gated polling.
 */
export default function AiOperationsPage() {
  return <AiOperationsOverviewScreen />;
}
