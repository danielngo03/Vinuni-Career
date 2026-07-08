import type { ApiErrorCode } from "./types";

/**
 * Typed API error. Only carries user-safe fields. We never surface raw
 * internal/provider details, stack traces, or upstream status text to the UI
 * (CLAUDE.md / docs/SECURITY_PRIVACY.md).
 */
export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status: number;
  readonly requestId?: string;
  readonly details?: Record<string, unknown>;

  constructor(params: {
    code: ApiErrorCode;
    message: string;
    status: number;
    requestId?: string;
    details?: Record<string, unknown>;
  }) {
    super(params.message);
    this.name = "ApiError";
    this.code = params.code;
    this.status = params.status;
    this.requestId = params.requestId;
    this.details = params.details;
  }

  /** True when re-authentication should be triggered. */
  get isAuthError(): boolean {
    return this.code === "AUTH_REQUIRED" || this.status === 401;
  }

  /** True when the user lacks permission (show permission state, not error). */
  get isPermissionError(): boolean {
    return this.code === "PERMISSION_DENIED" || this.status === 403;
  }

  get isNotFound(): boolean {
    return this.code === "RESOURCE_NOT_FOUND" || this.status === 404;
  }

  /** True on a state/version conflict (illegal transition, stale version). */
  get isConflict(): boolean {
    return this.code === "CONFLICT" || this.status === 409;
  }

  /** True when the server rejected the payload (e.g. missing required field). */
  get isValidation(): boolean {
    return this.code === "VALIDATION_FAILED" || this.status === 422;
  }
}

const KNOWN_CODES: ReadonlySet<string> = new Set<ApiErrorCode>([
  "AUTH_REQUIRED",
  "PERMISSION_DENIED",
  "RESOURCE_NOT_FOUND",
  "VALIDATION_FAILED",
  "CONFLICT",
  "RATE_LIMITED",
  "QUOTA_EXCEEDED",
  "PAYMENT_REQUIRED",
  "AI_UNAVAILABLE",
  "INTERNAL_ERROR",
  "NETWORK_ERROR",
  "UNKNOWN_ERROR",
]);

export function normalizeCode(code: string | undefined): ApiErrorCode {
  if (code && KNOWN_CODES.has(code)) return code as ApiErrorCode;
  return "UNKNOWN_ERROR";
}
