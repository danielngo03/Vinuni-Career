import type { OnboardingStep } from "@/lib/api/onboarding";
import type { Persona } from "@/stores/auth-store";

export const ONBOARDING_STEP_ROUTES: Record<OnboardingStep, string> = {
  role_select: "/onboarding/role",
  seeker_type: "/onboarding/seeker-type",
  seeker_profile: "/onboarding/seeker-profile",
  student_verify: "/onboarding/student-verify",
  employer_info: "/onboarding/employer-info",
  employer_docs: "/onboarding/employer-docs",
  pending: "/onboarding/pending",
  complete: "/",
};

export function onboardingStepHref(step: OnboardingStep | null | undefined): string {
  return ONBOARDING_STEP_ROUTES[step ?? "role_select"] ?? ONBOARDING_STEP_ROUTES.role_select;
}

export function workspaceHomeHref(persona: Persona | null | undefined): string {
  if (persona === "partner") return "/partner/dashboard";
  if (persona === "university") return "/university/dashboard";
  return "/student/dashboard";
}
