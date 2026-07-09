import { PartnerCommandCenter } from "@/components/dashboards/partner-command-center";

// `/partner/ops` now renders the same flagship command center as the dashboard
// (the IA merged "Recruiting ops" into "Dashboard"). Kept so existing links and
// bookmarks still resolve.
export default function PartnerOpsPage() {
  return <PartnerCommandCenter />;
}

