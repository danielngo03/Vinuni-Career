import { api, apiUpload } from "./client";
import { ApiError } from "./errors";
import type { ApiEnvelope } from "./types";
import type { CvDetail } from "./cv";

/* ------------------------------------------------------------------ *
 * CV Ingestion (preview-first upload -> ingest -> review -> import)   *
 * docs/CV_INGESTION_EXTRACTION_SPEC.md §2/§5.                          *
 *                                                                     *
 * These endpoints model the product flow:                             *
 *   1. POST /cv-uploads            -> store original + preview meta    *
 *   2. POST /cv-uploads/{id}/ingest-> start/resume async ingestion     *
 *   3. GET  /cv-ingestions/{id}    -> poll user-safe status            *
 *   4. POST /cv-ingestions/{id}/import -> create a new/draft builder CV*
 *                                                                     *
 * Statuses + labels are user-safe (no engine/model/provider names, no  *
 * raw confidence). `review_fields[].needs_review` drives the editable   *
 * "Check this" badge — NOT a numeric score.                            *
 * ------------------------------------------------------------------ */

/** Async ingestion lifecycle (backend `catalog.INGEST_*`). */
export type IngestionStatus =
  | "queued"
  | "checking"
  | "reading"
  | "improving_layout"
  | "reading_scanned"
  | "preparing_review"
  | "needs_review"
  | "ready"
  | "failed";

/** Statuses at which polling stops. */
export const TERMINAL_INGESTION_STATUSES: ReadonlySet<string> = new Set([
  "needs_review",
  "ready",
  "failed",
]);

/** The friendly "stepper" order shown while processing (queued is folded in). */
export const INGESTION_PROGRESS_STEPS: IngestionStatus[] = [
  "checking",
  "reading",
  "improving_layout",
  "reading_scanned",
  "preparing_review",
];

/**
 * Next-action tokens the backend may return per terminal status
 * (`ingestion_service._next_actions` + `cv_validation.copy_for`). `wait` is the
 * non-terminal placeholder; all others map to a concrete affordance.
 */
export type IngestionNextAction =
  | "import_to_cv"
  | "keep_original"
  | "upload_another"
  | "review_fields"
  | "create_from_template"
  | "use_existing"
  | "wait";

/**
 * Quality codes that can appear on a terminal ingestion. `null` on a clean
 * `ready`/`needs_review`. Drives the §7 failure/recovery copy + actions.
 */
export type IngestionQualityCode =
  | "UNSUPPORTED_FILE_TYPE"
  | "FILE_TOO_LARGE"
  | "FILE_REJECTED_SECURITY"
  | "PASSWORD_PROTECTED_FILE"
  | "CORRUPT_FILE"
  | "DUPLICATE_FILE"
  | "BLANK_DOCUMENT"
  | "LOW_QUALITY_SCAN"
  | "NOT_A_CV"
  | "INSUFFICIENT_CV_CONTENT"
  | "LANGUAGE_REVIEW_REQUIRED"
  | "REVIEW_REQUIRED"
  | "OK";

/** Preview/upload metadata for a freshly stored original (NOT builder content). */
export interface UploadPreview {
  document_id: string;
  filename: string;
  content_type: string;
  size: number;
  /** Page count when known (PDF); null for images / not-yet-processed files. */
  page_count: number | null;
  /**
   * Signed, token-authorized inline preview/original URL (`GET /cv-files/{token}`).
   * Renders the ORIGINAL document before any extraction. May be relative.
   */
  preview_url: string | null;
}

/**
 * One extracted field in the review screen. `needs_review` flags the editable
 * "Check this" badge. `source_span`/`page` anchor the field to the original
 * document for the side-by-side highlight (both optional / best-effort).
 */
export interface IngestionReviewField {
  path: string;
  value: string;
  needs_review: boolean;
  source_span?: string | null;
  page?: number | null;
}

/** User-safe ingestion status (`presenters.ingestion`). */
export interface Ingestion {
  id: string;
  ingestion_id: string;
  document_id: string;
  status: IngestionStatus | string;
  status_label: string;
  quality_code: IngestionQualityCode | string | null;
  quality_message: string | null;
  detected_language: string | null;
  mixed_language: boolean;
  review_fields: IngestionReviewField[];
  next_actions: (IngestionNextAction | string)[];
  /** Set after a successful import (idempotent re-import returns it). */
  imported_cv_id: string | null;
}

/** Body for `POST /cv-ingestions/{id}/import`. */
export interface ImportIngestionBody {
  title?: string;
  template_id?: string | null;
  /** Only a DRAFT CV may be targeted; accepted CVs are never overwritten. */
  target_cv_id?: string | null;
  fact_confirmation?: boolean;
  idempotency_key?: string | null;
  /**
   * Per-field review decisions applied to the draft before structuring. `path`
   * must be one the ingestion emitted in `review_fields` (others are ignored
   * server-side). `accepted: false` excludes the field from the imported draft
   * entirely (the explicit "reject" path); `accepted: true` (default) imports
   * `value` (the student's correction, or the original extracted value).
   */
  overrides?: { path: string; value: string; accepted?: boolean }[];
}

/**
 * True when a thrown error is the `422 VALIDATION_FAILED` per-field
 * confirmation gate (`details.reason === "fact_confirmation_required"`) raised
 * when a `needs_review` field was not explicitly accepted/edited/rejected
 * before import. `details.fields` lists the undecided `review_fields[].path`
 * values so the UI can re-highlight exactly those rows.
 */
export function parseFactConfirmationRequiredError(
  error: unknown,
): string[] | null {
  if (!(error instanceof ApiError)) return null;
  if (!error.isValidation) return null;
  const details = error.details ?? {};
  if (details.reason !== "fact_confirmation_required") return null;
  const fields = details.fields;
  return Array.isArray(fields) ? fields.filter((f): f is string => typeof f === "string") : [];
}

export const cvIngestionApi = {
  /** Store the original file; returns preview metadata (multipart). */
  async createUpload(
    file: File,
    idempotencyKey?: string,
  ): Promise<UploadPreview> {
    const form = new FormData();
    form.append("file", file);
    if (idempotencyKey) form.append("idempotency_key", idempotencyKey);
    const res = await apiUpload<ApiEnvelope<UploadPreview>>(
      "/cv-uploads",
      form,
    );
    return res.data;
  },

  /** Start or resume ingestion for a stored upload (idempotent/resumable). */
  startIngestion(
    documentId: string,
    idempotencyKey?: string,
  ): Promise<Ingestion> {
    return api.post<Ingestion>(`/cv-uploads/${documentId}/ingest`, {
      idempotency_key: idempotencyKey ?? null,
    });
  },

  /** Poll user-safe ingestion status. */
  getIngestion(ingestionId: string): Promise<Ingestion> {
    return api.get<Ingestion>(`/cv-ingestions/${ingestionId}`);
  },

  /** Confirm + import a reviewed ingestion into a NEW (or DRAFT) builder CV. */
  importIngestion(
    ingestionId: string,
    body: ImportIngestionBody,
  ): Promise<CvDetail> {
    return api.post<CvDetail>(`/cv-ingestions/${ingestionId}/import`, body);
  },
};

/* --------------------- imported-CV original linkage --------------------- */

/**
 * Best-effort, session-scoped memory of which original document an imported CV
 * came from, so the builder can show the original-document preview right after
 * import (`docs/CV_INGESTION_EXTRACTION_SPEC.md` §6). The durable path is a
 * `source_document_id` on the CV projection (tracked backend follow-up); this
 * keeps the feature working in-session without faking a backend field.
 */
export interface ImportOrigin {
  documentId: string;
  previewUrl: string | null;
  filename: string;
  contentType: string;
  pageCount: number | null;
}

const ORIGIN_PREFIX = "cv-import-origin:";

export function rememberImportOrigin(cvId: string, origin: ImportOrigin): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(
      `${ORIGIN_PREFIX}${cvId}`,
      JSON.stringify(origin),
    );
  } catch {
    /* storage unavailable (private mode / quota) — non-fatal */
  }
}

export function readImportOrigin(cvId: string): ImportOrigin | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(`${ORIGIN_PREFIX}${cvId}`);
    return raw ? (JSON.parse(raw) as ImportOrigin) : null;
  } catch {
    return null;
  }
}
