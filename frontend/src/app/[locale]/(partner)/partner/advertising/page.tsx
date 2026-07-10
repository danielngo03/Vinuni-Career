import { CampaignManagerScreen } from "@/components/advertising/campaign-manager-screen";

/**
 * Partner "Quảng cáo" — the campaign allocation-engine manager (spec §7.0). The
 * older target-based sponsored-placement screen still exists under
 * `partner-advertising-screen.tsx`; the allocation-engine campaign manager is
 * now the primary advertising surface (owner decision 2026-07-10).
 */
export default function PartnerAdvertisingPage() {
  return <CampaignManagerScreen />;
}
