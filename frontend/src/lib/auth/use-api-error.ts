"use client";

import { useTranslations } from "next-intl";
import type { Path, UseFormSetError, FieldValues } from "react-hook-form";
import { ApiError } from "@/lib/api";

/**
 * Maps an unknown thrown value to a localized, user-safe message.
 *
 * Priority: an auth-specific override (e.g. invalid credentials), then the
 * error-code copy, then the server-provided safe message, then a generic
 * fallback. Never surfaces raw internals (status text, provider details).
 */
export function useApiErrorMessage() {
  const t = useTranslations("errors");
  const tAuth = useTranslations("auth.apiErrors");

  return (error: unknown, opts?: { context?: "login" | "register" }): string => {
    if (!(error instanceof ApiError)) {
      return t("UNKNOWN_ERROR");
    }

    const reason =
      typeof error.details?.reason === "string"
        ? (error.details.reason as string)
        : undefined;

    // Resend/rate-limit cooldowns (forgot-password, verify-email resend,
    // resumed register) carry a backend-provided wait time — safe to show,
    // never inflated or guessed client-side.
    if (
      error.code === "RATE_LIMITED" &&
      (reason === "resend_cooldown" || reason === "rate_limited")
    ) {
      const seconds = error.details?.retry_after_seconds;
      if (typeof seconds === "number") {
        return tAuth("apiErrors.resendCooldown", { seconds });
      }
    }

    // Context-aware friendly overrides.
    if (opts?.context === "login") {
      if (reason === "email_not_verified") return tAuth("emailNotVerified");
      if (reason === "account_locked" || error.code === "RATE_LIMITED")
        return tAuth("accountLocked");
      if (error.status === 401 || error.code === "VALIDATION_FAILED")
        return tAuth("invalidCredentials");
    }
    if (opts?.context === "register" && error.code === "CONFLICT") {
      return tAuth("emailTaken");
    }

    if (t.has(error.code)) return t(error.code);
    return error.message || t("UNKNOWN_ERROR");
  };
}

/**
 * Extracts a backend-provided cooldown (seconds) from a resend/rate-limit
 * error, for disabling a resend control until it elapses. Returns null for
 * any other error shape — never invented client-side.
 */
export function getRetryAfterSeconds(error: unknown): number | null {
  if (!(error instanceof ApiError) || error.code !== "RATE_LIMITED") return null;
  const reason =
    typeof error.details?.reason === "string" ? error.details.reason : undefined;
  if (reason !== "resend_cooldown" && reason !== "rate_limited") return null;
  const seconds = error.details?.retry_after_seconds;
  return typeof seconds === "number" ? seconds : null;
}

/**
 * Applies server-side field validation errors to a react-hook-form instance.
 * Tolerates both `details: { field: msg }` and `details: { fields: {...} }`.
 */
export function applyFieldErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
): boolean {
  if (!(error instanceof ApiError) || error.code !== "VALIDATION_FAILED") {
    return false;
  }
  const details = error.details ?? {};
  const fields =
    details.fields && typeof details.fields === "object"
      ? (details.fields as Record<string, unknown>)
      : (details as Record<string, unknown>);

  let applied = false;
  for (const [field, message] of Object.entries(fields)) {
    if (typeof message === "string") {
      setError(field as Path<T>, { type: "server", message });
      applied = true;
    }
  }
  return applied;
}
