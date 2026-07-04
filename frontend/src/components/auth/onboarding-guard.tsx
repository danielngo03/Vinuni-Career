"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "@/i18n/navigation";
import { onboardingStepHref } from "@/lib/onboarding/routes";
import { useAuthStore } from "@/stores/auth-store";

// Routes exempt from onboarding enforcement
const ONBOARDING_PATHS = /^\/(?:[a-z]{2}\/)?onboarding\//;
const AUTH_PATHS = /^\/(?:[a-z]{2}\/)?auth\//;
const PUBLIC_PATHS = /^\/(?:[a-z]{2}\/)?(?:$|jobs|companies|events)/;

/**
 * Placed in the main authenticated layout.
 * When the signed-in user has not completed onboarding, redirects them to
 * the wizard at their current step, preserving wizard-internal navigation.
 */
export function OnboardingGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { status, onboardingComplete, onboardingStep, checkOnboarding } = useAuthStore();

  useEffect(() => {
    // Skip guard for auth/onboarding pages, public routes, and unauthenticated state
    if (status !== "authenticated") return;
    if (ONBOARDING_PATHS.test(pathname)) return;
    if (AUTH_PATHS.test(pathname)) return;
    if (PUBLIC_PATHS.test(pathname)) return;

    if (onboardingComplete === null) {
      // Not yet fetched — fetch now
      checkOnboarding();
      return;
    }

    if (!onboardingComplete) {
      router.replace(onboardingStepHref(onboardingStep));
    }
  }, [status, onboardingComplete, onboardingStep, pathname, checkOnboarding, router]);

  return <>{children}</>;
}
