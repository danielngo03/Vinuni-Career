import type {
  CoarseSignalTags,
  CompanyDetail,
  CompanySummary,
  EventSummary,
  JobSummary,
  PublicEventDetail,
} from "@/lib/api";

/**
 * Pure builders for the privacy-safe coarse discovery signals a rendered item
 * carries (`docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md` §3). Every value here is
 * a COARSE, allowlisted signal the guest-session ranker
 * (`discovery/application/ranking_service`) already consumes; the backend
 * allowlist (`discovery/domain/allowlist.py`) is the final gate and drops
 * anything else.
 *
 * NON-NEGOTIABLE: only allowlisted keys may be produced here —
 * `categories` / `industries` / `role_families` / `company_ids` / `event_ids` /
 * `search_terms` (lists) and `work_mode` / `city` (scalars). NEVER emit PII,
 * exact location/GPS, raw CV/document text, third-party ad ids, or opaque
 * taxonomy UUIDs. `device_type` is attached downstream by the analytics client.
 *
 * These are intentionally framework-free (no React) so they are trivially unit
 * testable and reusable by list cards, mega-menu rows, and detail-page views.
 */

/** Coarse work-mode vocabulary (mirrors the backend allowlist `_WORK_MODES`). */
const WORK_MODES: ReadonlySet<string> = new Set(["onsite", "remote", "hybrid"]);

/** A valid coarse work-mode, or undefined (the backend drops invalid values). */
function coarseWorkMode(value: string | null | undefined): string | undefined {
  const token = value?.trim().toLowerCase();
  return token && WORK_MODES.has(token) ? token : undefined;
}

/** A trimmed non-empty scalar, or undefined. */
function scalar(value: string | null | undefined): string | undefined {
  const token = value?.trim();
  return token ? token : undefined;
}

/** A de-duped, non-empty list of trimmed tokens, or undefined when nothing survives. */
function list(...values: (string | null | undefined)[]): string[] | undefined {
  const out: string[] = [];
  for (const value of values) {
    const token = value?.trim();
    if (token && !out.includes(token)) out.push(token);
  }
  return out.length > 0 ? out : undefined;
}

/** Strip undefined / empty-list entries so the emitted payload stays minimal. */
function compact(tags: CoarseSignalTags): CoarseSignalTags {
  const out: CoarseSignalTags = {};
  for (const [key, value] of Object.entries(tags)) {
    if (value === undefined || value === null) continue;
    if (Array.isArray(value) && value.length === 0) continue;
    (out as Record<string, unknown>)[key] = value;
  }
  return out;
}

/** Job fields the signal builder reads. Kept structural so `RecommendedJob`,
 *  `JobSummary`, and `PublicJobDetail` all satisfy it. */
export type JobSignalSource = Pick<
  JobSummary,
  "org_id" | "location_type" | "location_city" | "role_family" | "industry_slug"
>;

/**
 * Coarse signals for a viewed/listed job. Emits `company_ids` (the owning org),
 * the coarse `work_mode` + `city` filter dimensions, and — when the backend
 * projection stamps them — `role_families` / `industries`. The raw
 * `industry_id` UUID is deliberately NOT emitted (a UUID is not a coarse
 * industry token). Pass the active search query via `searchTerms` when the item
 * is rendered inside a query context (job board).
 */
export function jobSignalTags(
  job: JobSignalSource,
  opts?: { searchTerms?: string[] },
): CoarseSignalTags {
  return compact({
    search_terms: opts?.searchTerms ? list(...opts.searchTerms) : undefined,
    company_ids: list(job.org_id),
    work_mode: coarseWorkMode(job.location_type),
    city: scalar(job.location_city),
    role_families: list(job.role_family),
    industries: list(job.industry_slug),
  });
}

/** Event fields the signal builder reads (satisfied by summary + detail). */
export type EventSignalSource = Pick<EventSummary | PublicEventDetail, "id" | "event_type">;

/**
 * Coarse signals for a viewed/listed event. Emits `event_ids` and the coarse
 * `event_type` as a `categories` signal. The venue/address is never emitted
 * (exact location is forbidden).
 */
export function eventSignalTags(event: EventSignalSource): CoarseSignalTags {
  return compact({
    event_ids: list(event.id),
    categories: list(event.event_type),
  });
}

/** Company fields the signal builder reads (satisfied by summary + detail). */
export type CompanySignalSource = Pick<CompanySummary | CompanyDetail, "id" | "industry">;

/**
 * Coarse signals for a viewed/listed company. Emits `company_ids` and — when
 * the company carries a coarse industry label — `industries`.
 */
export function companySignalTags(company: CompanySignalSource): CoarseSignalTags {
  return compact({
    company_ids: list(company.id),
    industries: list(company.industry),
  });
}
