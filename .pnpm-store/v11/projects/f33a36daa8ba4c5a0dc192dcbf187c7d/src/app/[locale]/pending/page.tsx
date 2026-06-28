import { ApiError } from "@/components/feedback/api-error";
import { PendingRegistrationScreen } from "@/features/onboarding/pending-registration";
import { BackendError, backendFetch } from "@/lib/api/server";
import type { PendingRegistration } from "@/lib/api/types";

export default async function PendingRegistrationPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  let registration: PendingRegistration | null = null;
  let message = "";
  try {
    registration = await backendFetch<PendingRegistration>("/registrations/me");
  } catch (error) {
    message =
      error instanceof BackendError
        ? error.message
        : "Unable to load the registration application.";
  }
  if (!registration) {
    return (
      <main className="flex min-h-screen items-center justify-center p-6">
        <div className="w-full max-w-xl">
          <ApiError description={message} />
        </div>
      </main>
    );
  }
  return (
    <PendingRegistrationScreen
      registration={registration}
      locale={locale}
    />
  );
}
