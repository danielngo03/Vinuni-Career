import { api, apiUpload } from "./client";
import { ApiError } from "./errors";
import { env } from "@/lib/env";
import type { ApiEnvelope, ApiListEnvelope } from "./types";

/* ------------------------------- Vocabularies ----------------------------- */

/**
 * Creation paths accepted by `POST /cvs` (docs/API_CONTRACTS.md). Only
 * `blank_template` is selectable in the create modal; `uploaded_import` and
 * `duplicate_existing` are produced by the upload/duplicate flows via their own
 * endpoints. There is no notes/profile/AI-draft creation path.
 */
export type CvCreationMode =
  | "blank_template"
  | "uploaded_import"
  | "duplicate_existing";

/** Creation modes a user can pick directly in the create modal. */
export const SELECTABLE_CREATION_MODES: CvCreationMode[] = [
  "blank_template",
  "uploaded_import",
  "duplicate_existing",
];

/**
 * Every parse-run `quality_code` we must render a friendly recovery card for
 * (docs/API_CONTRACTS.md + docs/EDGE_CASES_FAILURE_MODES.md). `OK` is internal.
 */
export type CvQualityCode =
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
  | "REVIEW_REQUIRED";

/**
 * Recovery actions the backend offers when the active-CV quota is reached
 * (`POST /cvs` / `POST /cvs/{id}/duplicate` -> 409 QUOTA_EXCEEDED). `archive`
 * and `delete_draft` are actionable in-app; `request_more_quota`/`upgrade` are
 * honest "coming soon" affordances (no billing/request backend exists yet).
 */
export type CvQuotaAction =
  | "archive_existing"
  | "delete_draft"
  | "request_more_quota"
  | "upgrade";

const KNOWN_QUOTA_ACTIONS: ReadonlySet<string> = new Set<CvQuotaAction>([
  "archive_existing",
  "delete_draft",
  "request_more_quota",
  "upgrade",
]);

/** Recovery actions surfaced by the backend in `next_actions`. */
export type CvNextAction =
  | "review_fields"
  | "upload_another"
  | "create_from_template"
  | "use_existing"
  | "import_to_cv";

export type ParseRunStatus =
  | "uploaded"
  | "virus_scanning"
  | "extracting"
  | "review_required"
  | "confirmed"
  | "ready"
  | "failed";

/** Terminal parse-run statuses — stop polling once reached. */
export const TERMINAL_PARSE_STATUSES: ReadonlySet<string> = new Set([
  "review_required",
  "confirmed",
  "ready",
  "failed",
]);

export type ExportStatus = "queued" | "processing" | "ready" | "failed";

/* ------------------------------- Wire types ------------------------------- */

/**
 * A template's `layout_schema`. Newer rows carry the full CV document theme (see
 * `frontend/src/components/cv/render/theme.ts` — the backend ships the identical
 * shape); older/legacy rows carry only `section_order` + a font hint. Every
 * field is optional so older rows still type-check; the renderer deep-merges
 * onto `DEFAULT_THEME`. Kept permissive (`[key: string]: unknown`) on purpose.
 */
export interface CvTemplateLayoutSchema {
  /** Legacy: canonical section order (superseded by `order`). */
  section_order?: string[];
  target_roles?: string[];
  strengths?: string[];
  page?: { size?: string; max_pages?: number };
  /** Legacy font hint (`sans`/`serif`) — superseded by `typography`. */
  typography?: { font?: string; base_pt?: number } & Record<string, unknown>;
  /** Full CV document theme fields (permissive; validated by `resolveTheme`). */
  version?: number;
  layout?: { kind?: string; sidebarWidthPct?: number; bodyColumns?: number };
  palette?: Record<string, string>;
  photo?: Record<string, unknown>;
  sectionStyle?: Record<string, unknown>;
  regions?: { sidebar?: string[]; main?: string[] };
  order?: string[];
  [key: string]: unknown;
}

export interface CvTemplate {
  id: string;
  key: string;
  name: string;
  name_vi?: string;
  name_en?: string;
  category: string;
  layout_schema?: CvTemplateLayoutSchema;
  is_active?: boolean;
  preview_url: string | null;
}

export interface AdminCvTemplateCreateBody {
  key: string;
  name_vi: string;
  name_en: string;
  category: string;
  layout_schema: Record<string, unknown>;
  is_active: boolean;
}

export type AdminCvTemplateUpdateBody = Partial<AdminCvTemplateCreateBody>;

/** Flexible section body. Summary-style uses `text`; list sections use `items`. */
export interface CvSectionItem {
  text?: string;
  [key: string]: unknown;
}
export interface CvSectionContent {
  text?: string;
  items?: CvSectionItem[];
  [key: string]: unknown;
}

export interface CvSection {
  id: string;
  section_type: string;
  title: string;
  sort_order: number;
  content: CvSectionContent;
  is_visible: boolean;
}

/* ------------------------------ Canvas / photo ----------------------------- */

/**
 * Presentation-only style hints for a canvas block. CV facts always stay in
 * the referenced section's `content` — style never carries text.
 */
export interface CvCanvasBlockStyle {
  align?: "left" | "center" | "right";
  fontSize?: "sm" | "md" | "lg";
  emphasis?: "normal" | "bold";
  [key: string]: unknown;
}

/** A single canvas layout entry (`PATCH /cvs/{id}/canvas` request/response). */
export interface CvCanvasBlock {
  id: string;
  type: string;
  section_id?: string | null;
  order: number;
  visible: boolean;
  style?: CvCanvasBlockStyle | null;
}

/** Typed contact-link kind — drives the renderer's per-link icon. */
export type CvLinkType =
  | "email"
  | "phone"
  | "website"
  | "linkedin"
  | "github"
  | "facebook"
  | "twitter"
  | "instagram"
  | "custom";

/**
 * Font-size steps allowed on a per-element override. Maps to a fixed pt bump in
 * the renderer (never a raw px value from the client).
 */
export type ElementStyleSize = "xs" | "sm" | "base" | "lg" | "xl" | "2xl";
export type ElementStyleWeight = "normal" | "medium" | "semibold" | "bold";
export type ElementStyleAlign = "left" | "center" | "right";

/**
 * Per-element presentation override written by the contextual text toolbar.
 * Keyed by the P2 `data-edit-path` grammar and stored in
 * `canvas.elementStyles = { [editPath]: ElementStyle }` (a sibling of
 * `canvas.theme`, design spec §data-contract 1). Every field is optional — an
 * empty object resets that element to the theme default. The backend validates
 * `font` against the theme font tokens, the size/weight/align enums, and a hex
 * regex; unknown keys are stripped.
 */
export interface ElementStyle {
  /** Font family token — one of the renderer `FontKind` values. */
  font?: "sans" | "serif" | "mono";
  size?: ElementStyleSize;
  weight?: ElementStyleWeight;
  italic?: boolean;
  align?: ElementStyleAlign;
  /** 6-digit hex (e.g. `#1a1a1a`). */
  color?: string;
}

/** The full per-CV element-style map (`editPath` → override). */
export type ElementStyleMap = Record<string, ElementStyle>;

export interface CvCanvasPhoto {
  url?: string | null;
  shape?: "circle" | "square" | "rounded" | null;
  crop?: { x: number; y: number; width: number; height: number } | null;
}

/** Raw `canvas` blob on `CvSummary`/`CvDetail` (`p.canvas_json`). */
export interface CvCanvas {
  blocks?: CvCanvasBlock[];
  page?: Record<string, unknown>;
  photo?: CvCanvasPhoto | null;
  /** Per-CV student theme overrides layered on the template (design spec §4.2). */
  theme?: CvCanvasTheme | null;
  /**
   * Per-element presentation overrides written by the contextual text toolbar,
   * keyed by the P2 `data-edit-path` grammar (design spec §data-contract 1).
   * Applied by the renderer per text node on top of the theme.
   */
  elementStyles?: ElementStyleMap | null;
  [key: string]: unknown;
}

export interface UpdateCvCanvasBody {
  blocks?: CvCanvasBlock[];
  page?: Record<string, unknown>;
  /**
   * Per-CV student theme overrides layered on the template
   * (`canvas.theme` — palette/typography/density recolour). Only the provided
   * keys are merged server-side; omit to leave the theme untouched. The backend
   * canvas PATCH accepts this alongside `blocks` (design spec §4.2).
   */
  theme?: CvCanvasTheme;
  /**
   * Full per-element style map (`{ [editPath]: ElementStyle }`). Sent as the
   * complete map — the client merges a single element change into the CV's
   * current map and PATCHes the whole thing (see {@link patchElementStyle}).
   * An entry with an empty object, or a removed key, resets that element to the
   * theme default. Omit to leave element styles untouched (design spec
   * §data-contract 1).
   */
  elementStyles?: ElementStyleMap;
  expected_version?: number;
}

/**
 * Student per-CV theme overrides stored in `canvas.theme`. Mirrors the
 * renderer's `PartialCvTheme` recolour groups (palette/typography/density);
 * kept permissive so future theme fields don't break the wire type.
 */
export interface CvCanvasTheme {
  palette?: Record<string, string>;
  typography?: { headingFont?: string; bodyFont?: string; scale?: string };
  sectionStyle?: { heading?: string; itemGap?: string };
  layout?: { kind?: string; sidebarWidthPct?: number; bodyColumns?: number };
  [key: string]: unknown;
}

export interface UpdateCvPhotoBody {
  /** Omit to remove the photo. */
  file?: File | null;
  cropX?: number;
  cropY?: number;
  cropWidth?: number;
  cropHeight?: number;
  shape?: "circle" | "square" | "rounded";
  expectedVersion?: number;
}

export interface CvSummary {
  id: string;
  title: string;
  source_type: string;
  source_label: string;
  template_id: string | null;
  language: string;
  status: string;
  status_label: string;
  version: number;
  last_edited_at: string | null;
  canvas?: CvCanvas;
}

/**
 * Quota meta returned in `GET /cvs` `meta`. Drives the active-CV counter and
 * the disabled/secondary create + duplicate states (docs/CV_STUDIO_SPEC.md §5:
 * default 5 active CV library items unless the tier limit is changed).
 */
export interface CvLibraryMeta {
  active_cv_limit: number;
  active_cv_used: number;
  can_create: boolean;
  quota_reset_at: string | null;
  quota_source: string;
}

/** `GET /cvs` list envelope, including the typed quota `meta`. */
export interface CvListResult extends ApiListEnvelope<CvSummary> {
  meta?: CvLibraryMeta;
}

/** Parsed, user-safe view of a 409 `cv_quota_reached` response. */
export interface CvQuotaInfo {
  /** Server-localized, user-safe message (shown as the primary text). */
  message: string;
  current: number;
  limit: number;
  actions: CvQuotaAction[];
}

export interface CvDetail extends CvSummary {
  sections: CvSection[];
  created_at: string;
  /**
   * Optional: the latest `cv_versions` UUID needed to trigger an export. The
   * current backend projection does not return it yet; the export panel reads it
   * here (or from `versions[0]`) the moment the API exposes it. See handoff.
   */
  current_version_id?: string | null;
  versions?: CvVersionSummary[];
  /** Present when the CV was created with a pending AI suggestion to review. */
  pending_suggestion?: CvAiSuggestion | null;
  /**
   * True when this CV came from an uploaded file (PDF/image). Uploaded CVs are
   * viewed read-only (the student's own document) — never opened in the builder,
   * which is for template-created CVs only.
   */
  is_uploaded?: boolean;
  /** Signed preview URL of the original uploaded file (only for uploaded CVs). */
  original_preview_url?: string | null;
}

export interface CvVersionSummary {
  id: string;
  /** Monotonic version number (the live API field is `version`). */
  version: number;
  /** True for the head/current snapshot (equals `current_version_id`). */
  is_current?: boolean;
  change_source?: "manual" | "import" | "restore" | string | null;
  change_summary?: string | null;
  created_at?: string | null;
}

export interface CvReviewField {
  path: string;
  value: string;
  needs_review: boolean;
}

export interface CvParseRun {
  id: string;
  document_id: string;
  status: ParseRunStatus | string;
  status_label: string;
  quality_code: CvQualityCode | string;
  user_message: string;
  next_actions: (CvNextAction | string)[];
  detected_language: string | null;
  review_fields: CvReviewField[];
}

export interface CvUploadResult {
  document_id: string;
  parse_run_id: string;
  status: ParseRunStatus | string;
  next_action: CvNextAction | string;
}

export interface CvExport {
  id: string;
  export_id: string;
  cv_id: string;
  version_id: string;
  format: string;
  status: ExportStatus | string;
  status_label: string;
  download_url: string | null;
  created_at: string | null;
  completed_at: string | null;
}

/* ------------------------------- Job-fit ---------------------------------- */

/**
 * The six core HR fit criteria (0-100 each). These are deterministic
 * **product** scores derived from JD/CV evidence — NOT model confidence. Never
 * label them as "AI confidence" in the UI (docs/API_CONTRACTS.md §CV-To-Job
 * Fit, docs/CV_STUDIO_SPEC.md §3).
 */
export interface JobFitBands {
  skills: number;
  experience: number;
  scope: number;
  credentials: number;
  soft_skills: number;
  trajectory: number;
}

// ─── AI Suggestion types ────────────────────────────────────────────────────

/**
 * Task types the CV AI layer supports. Matches `catalog.AI_TASK_TYPES` in
 * `backend/app/modules/documents/domain/catalog.py`. Only surface user-facing
 * labels from the API response — never hard-code model/provider details.
 */
export type CvAiTaskType =
  | "draft_cv_from_profile"
  | "fill_cv_template_from_sources"
  | "generate_cv_bullets"
  | "rewrite_cv_section"
  | "optimize_cv_for_job"
  | "ats_keyword_suggestions"
  | "cv_fabrication_check"
  | "ai_edit_command";

export type CvAiSuggestionStatus =
  | "pending"
  | "processing"
  | "ready"
  | "accepted"
  | "rejected"
  | "failed"
  | "expired";

/** One CV section spec as returned inside the diff before/after envelopes. */
export interface CvAiSectionSpec {
  id?: string;
  title?: string;
  type?: string;
  content?: {
    items?: Array<{ text?: string; [k: string]: unknown }>;
    [k: string]: unknown;
  };
  [k: string]: unknown;
}

/** Diff produced by the AI layer (leak-safe — no model/prompt/token internals). */
export interface CvAiDiff {
  summary: string;
  /** Structured envelope — sections array contains CV section specs. */
  before: { sections: CvAiSectionSpec[] } | null;
  after: { sections: CvAiSectionSpec[] } | null;
  requires_fact_confirmation: boolean;
  /** false for advisory-only tasks (ats_keyword_suggestions, cv_fabrication_check). */
  applicable?: boolean;
  section_id?: string | null;
  section_title?: string | null;
  /** ATS task: keyword gap list. */
  keywords?: string[] | null;
  /** Fabrication check task: claims needing evidence. */
  unsupported_claims?: string[];
  assistant_note?: string;
}

/** Single AI suggestion as returned by the backend. */
export interface CvAiSuggestion {
  suggestion_id: string;
  id: string;
  cv_id: string;
  task_type: CvAiTaskType | string;
  task_label: string;
  status: CvAiSuggestionStatus;
  status_label: string;
  credits_charged: number;
  diff: CvAiDiff;
  ai_mode?: string | null;
}

export interface AiSuggestionSourceIds {
  profile?: boolean;
  uploaded_document_id?: string | null;
  cv_parse_run_id?: string | null;
  source_cv_id?: string | null;
}

export interface RequestAiSuggestionBody {
  task_type: CvAiTaskType | string;
  target_section_id?: string | null;
  job_id?: string | null;
  instruction?: string | null;
  raw_notes?: string | null;
  source_ids?: AiSuggestionSourceIds | null;
  idempotency_key?: string | null;
}

export interface AcceptAiSuggestionBody {
  accepted_diff?: Record<string, unknown> | null;
  fact_confirmation?: boolean;
  idempotency_key?: string | null;
}

/**
 * Natural-language CV edit request (`POST /cvs/{id}/ai-edit-command`). Always
 * resolves synchronously to a pending `CvAiSuggestion`-shaped diff — never
 * mutates the CV. Accept/reject reuse the standard suggestion endpoints.
 */
export interface AiEditCommandBody {
  instruction: string;
  target_section_id?: string | null;
  idempotency_key?: string | null;
}

// ─── Job-fit types ───────────────────────────────────────────────────────────

/** One scored CV in a job-fit ranking. */
export interface JobFitResult {
  cv_id: string;
  title: string;
  /** Overall product fit score, 0-100 integer. */
  score: number;
  bands: JobFitBands;
  /** JD skills found in the CV — rendered as positive chips. */
  matched_skills: string[];
  /** JD skills not yet evidenced — framed constructively, never as accusations. */
  gaps: string[];
  /** CV content is older than the stale window (`cv_stale_after_days`). */
  stale: boolean;
  last_updated_days: number;
  /**
   * Optional, output-guarded enrichment for the recommended CV only. `null` when
   * no provider is active or the call failed (then `ai_explanation_available` is
   * false and the explanation block is hidden — no error, no provider mention).
   */
  explanation: string | null;
}

/** Minimal target-job reference echoed back by the job-fit endpoint. */
export interface JobFitJobRef {
  id: string;
  title: string;
  company: { display_name: string };
}

/** `"low_signal"` when the JD yields fewer than 2 parseable requirements. */
export type JobFitSignal = "ok" | "low_signal";

/** `GET /cvs/job-fit?job_id=…` response (owner-only; scores the caller's CVs). */
export interface JobFit {
  job: JobFitJobRef;
  /** Highest-scoring CV id, or null when the caller has no eligible CVs. */
  recommended_cv_id: string | null;
  results: JobFitResult[];
  signal: JobFitSignal;
  /** False when deterministic-only (offline/degraded) — hide the explanation. */
  ai_explanation_available: boolean;
}

/* ------------------------------- Request bodies --------------------------- */

export interface CvSourceInput {
  import_profile?: boolean;
  uploaded_document_id?: string | null;
  cv_parse_run_id?: string | null;
  source_cv_id?: string | null;
  source_cv_version_id?: string | null;
  raw_notes?: string | null;
}

export interface CreateCvBody {
  title: string;
  template_id?: string | null;
  creation_mode: CvCreationMode;
  language?: string;
  source?: CvSourceInput | null;
}

export interface UpdateCvBody {
  title?: string;
  language?: string;
  status?: string;
  template_id?: string | null;
  expected_version?: number;
}

export interface SectionUpsertBody {
  section_type?: string | null;
  title?: string | null;
  sort_order?: number | null;
  is_visible?: boolean | null;
  content?: CvSectionContent | null;
  expected_version?: number | null;
}

export interface SectionUpsertResult {
  section: CvSection;
  cv_version: number;
}

export interface DuplicateCvBody {
  title?: string | null;
  template_id?: string | null;
  target_job_id?: string | null;
  idempotency_key?: string | null;
}

export interface ExportCvBody {
  version_id: string;
  format?: string;
  idempotency_key?: string | null;
}

/* --------------------------------- Helpers -------------------------------- */

/** RFC4122-ish key for idempotent POSTs (upload, duplicate, export). */
export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `idem_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

/* --------------------------------- Calls ---------------------------------- */

export const cvApi = {
  listTemplates(): Promise<CvTemplate[]> {
    return api.get<CvTemplate[]>("/cv-templates");
  },

  listAdminTemplates(): Promise<CvTemplate[]> {
    return api.get<CvTemplate[]>("/admin/cv-templates");
  },

  createTemplate(body: AdminCvTemplateCreateBody): Promise<CvTemplate> {
    return api.post<CvTemplate>("/admin/cv-templates", body);
  },

  updateTemplate(
    templateId: string,
    body: AdminCvTemplateUpdateBody,
  ): Promise<CvTemplate> {
    return api.patch<CvTemplate>(`/admin/cv-templates/${templateId}`, body);
  },

  list(opts?: {
    cursor?: string | null;
    limit?: number;
  }): Promise<CvListResult> {
    return api.list<CvSummary>("/cvs", {
      query: { cursor: opts?.cursor ?? undefined, limit: opts?.limit },
    }) as Promise<CvListResult>;
  },

  get(cvId: string): Promise<CvDetail> {
    return api.get<CvDetail>(`/cvs/${cvId}`);
  },

  /**
   * Rank the caller's active CVs against a target job (owner-only `cv:read`).
   * Read-only; deterministic 0-100 product score per CV plus an optional
   * AI explanation for the recommended CV. Never call for guests/partners.
   */
  jobFit(jobId: string): Promise<JobFit> {
    return api.get<JobFit>("/cvs/job-fit", { query: { job_id: jobId } });
  },

  /** Immutable version history, newest-first (head has `is_current: true`). */
  listVersions(cvId: string): Promise<CvVersionSummary[]> {
    return api.get<CvVersionSummary[]>(`/cvs/${cvId}/versions`);
  },

  /** Append a new section; bumps the CV version + creates a snapshot. */
  addSection(cvId: string, body: SectionUpsertBody): Promise<SectionUpsertResult> {
    return api.post<SectionUpsertResult>(`/cvs/${cvId}/sections`, body);
  },

  /** Restore a prior snapshot (non-destructive; returns full CV detail). */
  restoreVersion(
    cvId: string,
    versionId: string,
    expectedVersion?: number,
  ): Promise<CvDetail> {
    return api.post<CvDetail>(`/cvs/${cvId}/versions/${versionId}/restore`, {
      expected_version: expectedVersion,
    });
  },

  create(body: CreateCvBody): Promise<CvDetail> {
    return api.post<CvDetail>("/cvs", body);
  },

  /**
   * Commit a draft CV to the library (analyzed / matching-ready). Draft CVs are
   * unlimited scratch and cannot be used to apply or job-fit; finalizing
   * validates the CV is non-empty, enforces the library quota (max 5 `ready`
   * CVs), and flips `status` to `ready`. Returns the full detail.
   *
   * Errors to handle at the call site:
   *  - `409 QUOTA_EXCEEDED` (`details.reason === "cv_quota_reached"`) — parse
   *    with {@link parseCvQuotaError} and open the quota recovery dialog.
   *  - a user-safe empty-CV error (e.g. `422`/`409` with a "CV trống" message) —
   *    surface `error.message` inline; do not crash.
   * Idempotent: an already-`ready` CV returns its current detail (no re-count).
   */
  finalize(cvId: string): Promise<CvDetail> {
    return api.post<CvDetail>(`/cvs/${cvId}/finalize`, {});
  },

  update(cvId: string, body: UpdateCvBody): Promise<CvDetail> {
    return api.patch<CvDetail>(`/cvs/${cvId}`, body);
  },

  /** Delete a CV (soft-delete; removes it from the library). */
  remove(cvId: string): Promise<void> {
    return api.delete<void>(`/cvs/${cvId}`);
  },

  upsertSection(
    cvId: string,
    sectionId: string,
    body: SectionUpsertBody,
  ): Promise<SectionUpsertResult> {
    return api.patch<SectionUpsertResult>(
      `/cvs/${cvId}/sections/${sectionId}`,
      body,
    );
  },

  duplicate(cvId: string, body: DuplicateCvBody): Promise<CvDetail> {
    return api.post<CvDetail>(`/cvs/${cvId}/duplicate`, body);
  },

  /**
   * Partial canvas layout update (blocks/page; versioned, non-destructive).
   * Only the provided keys are replaced — omit `blocks` to leave block layout
   * untouched. Returns the full CV detail (including the merged `canvas`).
   */
  updateCanvas(cvId: string, body: UpdateCvCanvasBody): Promise<CvDetail> {
    return api.patch<CvDetail>(`/cvs/${cvId}/canvas`, body);
  },

  /** Replace/crop the CV profile photo, or remove it by omitting `file`. */
  async updatePhoto(cvId: string, body: UpdateCvPhotoBody): Promise<CvDetail> {
    const form = new FormData();
    if (body.file) form.append("file", body.file);
    if (body.cropX !== undefined) form.append("crop_x", String(body.cropX));
    if (body.cropY !== undefined) form.append("crop_y", String(body.cropY));
    if (body.cropWidth !== undefined) form.append("crop_width", String(body.cropWidth));
    if (body.cropHeight !== undefined) form.append("crop_height", String(body.cropHeight));
    if (body.shape) form.append("shape", body.shape);
    if (body.expectedVersion !== undefined) {
      form.append("expected_version", String(body.expectedVersion));
    }
    const res = await apiUpload<ApiEnvelope<CvDetail>>(`/cvs/${cvId}/photo`, form, {
      method: "PATCH",
    });
    return res.data;
  },

  /** Multipart upload via the shared auth-aware multipart helper. */
  async upload(file: File, idempotencyKey: string): Promise<CvUploadResult> {
    const form = new FormData();
    form.append("file", file);
    form.append("idempotency_key", idempotencyKey);
    const res = await apiUpload<ApiEnvelope<CvUploadResult>>(
      "/cvs/upload",
      form,
    );
    return res.data;
  },

  getParseRun(parseRunId: string): Promise<CvParseRun> {
    return api.get<CvParseRun>(`/cvs/parse-runs/${parseRunId}`);
  },

  createExport(cvId: string, body: ExportCvBody): Promise<CvExport> {
    return api.post<CvExport>(`/cvs/${cvId}/export`, {
      format: "pdf",
      ...body,
    });
  },

  getExport(exportId: string): Promise<CvExport> {
    return api.get<CvExport>(`/cv-exports/${exportId}`);
  },

  // ── AI Suggestions ────────────────────────────────────────────────────────

  getSuggestion(cvId: string, suggestionId: string): Promise<CvAiSuggestion> {
    return api.get<CvAiSuggestion>(
      `/cvs/${cvId}/ai-suggestions/${suggestionId}`,
    );
  },

  requestAiSuggestion(
    cvId: string,
    body: RequestAiSuggestionBody,
  ): Promise<CvAiSuggestion> {
    return api.post<CvAiSuggestion>(`/cvs/${cvId}/ai-suggestions`, body);
  },

  acceptAiSuggestion(
    cvId: string,
    suggestionId: string,
    body: AcceptAiSuggestionBody,
  ): Promise<CvAiSuggestion> {
    return api.post<CvAiSuggestion>(
      `/cvs/${cvId}/ai-suggestions/${suggestionId}/accept`,
      body,
    );
  },

  rejectAiSuggestion(
    cvId: string,
    suggestionId: string,
  ): Promise<CvAiSuggestion> {
    return api.post<CvAiSuggestion>(
      `/cvs/${cvId}/ai-suggestions/${suggestionId}/reject`,
      {},
    );
  },

  /**
   * Natural-language CV edit command. Always returns a pending diff (never
   * mutates the CV) — accept/reject via `acceptAiSuggestion`/`rejectAiSuggestion`.
   */
  requestAiEditCommand(
    cvId: string,
    body: AiEditCommandBody,
  ): Promise<CvAiSuggestion> {
    return api.post<CvAiSuggestion>(`/cvs/${cvId}/ai-edit-command`, body);
  },
};

/**
 * Detects an active-CV quota-reached error (409 QUOTA_EXCEEDED with
 * `details.reason === "cv_quota_reached"`) and returns a user-safe view for the
 * recovery modal. Returns null for any other error so callers fall back to the
 * normal toast/inline error path. Never surfaces internal codes — only the
 * server-localized message plus the machine `actions` tokens.
 */
export function parseCvQuotaError(error: unknown): CvQuotaInfo | null {
  if (!(error instanceof ApiError)) return null;
  if (error.code !== "QUOTA_EXCEEDED") return null;
  const details = error.details ?? {};
  if (details.reason !== "cv_quota_reached") return null;
  const actions = Array.isArray(details.actions)
    ? (details.actions.filter(
        (a): a is CvQuotaAction =>
          typeof a === "string" && KNOWN_QUOTA_ACTIONS.has(a),
      ))
    : [];
  return {
    message: error.message,
    current: typeof details.current === "number" ? details.current : 0,
    limit: typeof details.limit === "number" ? details.limit : 0,
    actions,
  };
}

/**
 * True when a thrown error is a `422 VALIDATION_FAILED` raised because a
 * creation `source` was missing/empty for a mode that requires one
 * (`details.reason === "source_required"`, e.g. `details.field === "raw_notes"`
 * for a blank/whitespace `raw_notes` source; docs/API_CONTRACTS.md §POST /cvs).
 * Lets callers render an inline field error instead of a toast. Pass `field` to
 * scope the check to a specific input.
 */
export function isCvSourceRequiredError(
  error: unknown,
  field?: string,
): boolean {
  if (!(error instanceof ApiError)) return false;
  if (error.code !== "VALIDATION_FAILED") return false;
  const details = error.details ?? {};
  if (details.reason !== "source_required") return false;
  if (field !== undefined && details.field !== field) return false;
  return true;
}

/**
 * Merge a single element's style change into the CV's current element-style map
 * and return the FULL next map (the shape the canvas PATCH expects). Passing an
 * empty `patch` — or a `patch` that clears every field — removes the entry so
 * the element falls back to the theme default. Pure; never mutates `current`.
 *
 * Usage (design spec §4 contextual toolbar):
 *   const next = patchElementStyle(cv.canvas?.elementStyles, editPath, { weight: "bold" });
 *   await cvApi.updateCanvas(cvId, { elementStyles: next, expected_version });
 */
export function patchElementStyle(
  current: ElementStyleMap | null | undefined,
  editPath: string,
  patch: ElementStyle,
): ElementStyleMap {
  const next: ElementStyleMap = { ...(current ?? {}) };
  const merged: ElementStyle = { ...next[editPath] };
  for (const [key, value] of Object.entries(patch) as [keyof ElementStyle, unknown][]) {
    if (value === undefined || value === null || value === "") {
      delete merged[key];
    } else {
      // Each key is narrowed by ElementStyle; the runtime value came from a
      // typed toolbar control, so this assignment is sound.
      (merged as Record<string, unknown>)[key] = value;
    }
  }
  if (Object.keys(merged).length === 0) {
    delete next[editPath];
  } else {
    next[editPath] = merged;
  }
  return next;
}

/**
 * Resolve a signed download URL to an absolute URL. The backend returns an
 * absolute `cv-files` URL already; this guards against relative paths.
 */
export function resolveDownloadUrl(url: string): string {
  if (url.startsWith("http")) return url;
  const base = env.apiBaseUrl.replace(/\/api\/v1$/, "");
  return `${base}${url.startsWith("/") ? "" : "/"}${url}`;
}
