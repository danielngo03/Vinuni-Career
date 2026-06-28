import { ApiError } from "@/components/feedback/api-error";
import { UniversityDashboardScreen } from "@/features/university/university-dashboard";
import { backendFetch, BackendError } from "@/lib/api/server";
import type {
  RegistrationQueueItem,
  UniversityDashboard,
  VerificationPolicy,
} from "@/lib/api/types";

export default async function UniversityPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  let data: UniversityDashboard | null = null;
  let registrations: RegistrationQueueItem[] = [];
  let policies: VerificationPolicy[] = [];
  let message = "";
  try {
    [data, registrations, policies] = await Promise.all([
      backendFetch<UniversityDashboard>("/dashboard/university"),
      backendFetch<RegistrationQueueItem[]>("/registrations/review-queue"),
      Promise.all([
        backendFetch<VerificationPolicy>(
          "/registrations/verification-policy/STUDENT",
        ),
        backendFetch<VerificationPolicy>(
          "/registrations/verification-policy/PARTNER",
        ),
      ]),
    ]);
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
  return (
    <UniversityDashboardScreen
      data={data}
      registrations={registrations}
      policies={policies}
      locale={locale}
    />
  );
}
