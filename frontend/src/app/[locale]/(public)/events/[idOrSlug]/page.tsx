import { PublicEventDetail } from "@/components/events/public-event-detail";

export default async function PublicEventDetailPage({
  params,
}: {
  params: Promise<{ idOrSlug: string }>;
}) {
  const { idOrSlug } = await params;
  return <PublicEventDetail eventId={idOrSlug} />;
}
