"use client";

import { ShieldWarning, SignIn } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { EmptyState } from "@/components/ui";
import { ApiError } from "@/lib/api";

/**
 * Renders the shared permission/auth empty state when `error` is a 403/401
 * from one of the `career_services_*` resource capabilities, else null. Every
 * career-services section gates independently — a counselor may have
 * `career_services_cohorts` but not `career_services_reporting`, etc.
 */
export function CareerServicesPermissionGate({
  error,
  bodyOverride,
}: {
  error: unknown;
  bodyOverride?: string;
}) {
  const tStates = useTranslations("states");
  const tCs = useTranslations("careerServices");

  if (!(error instanceof ApiError)) return null;
  if (!error.isPermissionError && !error.isAuthError) return null;

  return (
    <EmptyState
      kind={error.isPermissionError ? "permission" : "auth"}
      icon={error.isPermissionError ? ShieldWarning : SignIn}
      title={
        error.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")
      }
      description={
        error.isPermissionError
          ? (bodyOverride ?? tCs("permissionBody"))
          : tStates("authBody")
      }
    />
  );
}
