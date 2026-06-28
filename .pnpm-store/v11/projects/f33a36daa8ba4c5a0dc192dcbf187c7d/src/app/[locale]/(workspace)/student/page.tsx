import { ApiError } from "@/components/feedback/api-error";
import { StudentDashboardScreen } from "@/features/student/student-dashboard";
import type { StudentDashboard } from "@/lib/api/types";
import { backendFetch, BackendError } from "@/lib/api/server";

export default async function StudentPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  let data: StudentDashboard | null = null;
  let message = "";
  try {
    data = await backendFetch<StudentDashboard>("/dashboard/student");
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
  return <StudentDashboardScreen data={data} locale={locale} />;
}
