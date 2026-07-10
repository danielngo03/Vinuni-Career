import { CampaignQueueScreen } from "@/components/advertising/campaign-queue-screen";

/**
 * University "Quảng cáo" governance — the campaign allocation-engine review
 * queue (spec §7.0): approve/reject/mark-paid/pause/disable/relabel with the
 * spend roll-up. The older placement-oversight screen still lives under
 * `advertising-oversight-screen.tsx`; the campaign queue is now the primary
 * advertising governance surface (owner decision 2026-07-10).
 */
export default function UniversityAdvertisingPage() {
  return <CampaignQueueScreen />;
}
