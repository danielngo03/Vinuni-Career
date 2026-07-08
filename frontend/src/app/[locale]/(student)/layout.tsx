import { StudentShell } from "@/components/layout/student-shell";
import { OnboardingGuard } from "@/components/auth/onboarding-guard";

export default function StudentLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <OnboardingGuard>
      <StudentShell>{children}</StudentShell>
    </OnboardingGuard>
  );
}
