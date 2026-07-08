import { WorkspaceShell } from "@/components/layout/workspace-shell";
import { OnboardingGuard } from "@/components/auth/onboarding-guard";

export default function PartnerLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <OnboardingGuard>
      <WorkspaceShell persona="partner">{children}</WorkspaceShell>
    </OnboardingGuard>
  );
}
