/**
 * Wire types mirroring docs/API_CONTRACTS.md standard response shapes.
 */

export interface ApiEnvelope<T> {
  data: T;
  meta?: Record<string, unknown>;
}

export interface ApiPage {
  next_cursor: string | null;
  limit: number;
  /** Total matching rows, when the endpoint computes it (e.g. companies/jobs). */
  total?: number;
}

export interface ApiListEnvelope<T> {
  data: T[];
  page: ApiPage;
  /** Endpoint-specific metadata (e.g. CV library quota); narrowed per endpoint. */
  meta?: unknown;
}

/** Error code families from docs/API_CONTRACTS.md. */
export type ApiErrorCode =
  | "AUTH_REQUIRED"
  | "PERMISSION_DENIED"
  | "RESOURCE_NOT_FOUND"
  | "VALIDATION_FAILED"
  | "CONFLICT"
  | "RATE_LIMITED"
  | "QUOTA_EXCEEDED"
  | "PAYMENT_REQUIRED"
  | "AI_UNAVAILABLE"
  | "INTERNAL_ERROR"
  // Client-synthesized codes (network / parse failures):
  | "NETWORK_ERROR"
  | "UNKNOWN_ERROR";

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    request_id?: string;
  };
}
