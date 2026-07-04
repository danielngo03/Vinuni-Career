import { PartnerDetailScreen } from "@/components/university/partner-detail-screen";

export default async function UniversityPartnerDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <PartnerDetailScreen orgId={id} />;
}
