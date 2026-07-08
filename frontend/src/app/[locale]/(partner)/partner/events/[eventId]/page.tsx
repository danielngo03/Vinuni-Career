import { PartnerEventDetailScreen } from "@/components/events/partner-event-detail-screen";

export default async function PartnerEventDetailPage({
  params,
}: {
  params: Promise<{ eventId: string }>;
}) {
  const { eventId } = await params;
  return <PartnerEventDetailScreen eventId={eventId} />;
}
