import { CompanyDetailScreen } from "@/components/companies/company-detail-screen";

export default async function PublicCompanyDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return <CompanyDetailScreen slug={slug} />;
}
