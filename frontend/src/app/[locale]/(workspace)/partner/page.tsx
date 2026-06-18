import { ApiError } from "@/components/feedback/api-error";
import { PartnerDashboardScreen } from "@/features/partner/partner-dashboard";
import { backendFetch, BackendError } from "@/lib/api/server";
import type { PartnerDashboard } from "@/lib/api/types";

export default async function PartnerPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  let data: PartnerDashboard | null = null;
  let message = "";
  try {
    data = await backendFetch<PartnerDashboard>("/dashboard/partner");
  } catch (error) {
    message =
      error instanceof BackendError
        ? error.message
        : "Backend is unavailable. Start FastAPI and seed demo data.";
  }
  if (!data) {
    return (
      <div className="p-6">
        <ApiError description={message} />
      </div>
    );
  }
  return <PartnerDashboardScreen data={data} locale={locale} />;
}
