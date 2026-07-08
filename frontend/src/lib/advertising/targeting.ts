/**
 * Audience-targeting descriptor builder + vocabularies (pure).
 *
 * Mirrors the backend contract (`advertising/domain/targeting.py`): a partner
 * attaches a small, allowlist-safe audience descriptor to a sponsored placement
 * so a paid slot reaches RELEVANT viewers instead of "newest campaign wins".
 *
 * NON-NEGOTIABLE: only the SIX allowlisted, privacy-safe dimensions are ever
 * offered or emitted (`region`, `industry`, `role_family`, `work_mode`,
 * `student_segment`, `language`). Any other key is dropped here and rejected by
 * the backend — a placement can NEVER target a PII / sensitive category. Modes:
 *  - `automatic`  broad reach; no dimensions (the default).
 *  - `manual`     partner-declared allowlisted values per dimension.
 *  - `university_restricted`  set by the university; the partner may NOT edit it
 *    (the partner write path 422s `restricted_by_university`).
 *
 * These builders are framework-free so they are trivially unit-testable and
 * reusable by the placement form + read-only restricted display.
 */

import type {
  TargetingDescriptor,
  TargetingDimension,
  TargetingMode,
} from "@/lib/api";
import { TARGETING_DIMENSIONS } from "@/lib/api";

export { TARGETING_DIMENSIONS };
export type { TargetingDescriptor, TargetingDimension, TargetingMode };

/** Modes a PARTNER may set on their own placement (never self-restrict). */
export const PARTNER_MODES: TargetingMode[] = ["automatic", "manual"];

export const MODE_AUTOMATIC = "automatic" as const;
export const MODE_MANUAL = "manual" as const;
export const MODE_UNIVERSITY_RESTRICTED = "university_restricted" as const;

const ALL_MODES: ReadonlySet<string> = new Set<TargetingMode>([
  MODE_AUTOMATIC,
  MODE_MANUAL,
  MODE_UNIVERSITY_RESTRICTED,
]);

/** A validated descriptor whose `mode` is narrowed to a known mode. */
export interface NormalizedTargeting {
  mode: TargetingMode;
  dimensions: Partial<Record<TargetingDimension, string[]>>;
}

/* --------------------------------------------------------------------------- *
 * Closed value vocabularies (mirror the backend clamps)                       *
 * --------------------------------------------------------------------------- */

/** `work_mode` values the backend accepts (others are dropped). */
export const WORK_MODE_VALUES = ["onsite", "remote", "hybrid"] as const;
/** `student_segment` values the backend accepts. */
export const STUDENT_SEGMENT_VALUES = ["student", "alumni", "guest"] as const;
/** `language` values the backend accepts. */
export const LANGUAGE_VALUES = ["vi", "en"] as const;
/**
 * `role_family` values (mirror `discovery/domain/taxonomy._ROLE_FAMILIES`). This
 * is the coarse family the ranker derives from a job title, so a partner picking
 * one of these targets the SAME token the viewer signal carries.
 */
export const ROLE_FAMILY_VALUES = [
  "software_engineering",
  "data_ai",
  "product",
  "design",
  "marketing",
  "sales_bizdev",
  "finance",
  "operations",
  "hr_people",
  "customer",
] as const;

/**
 * Dimensions with a fixed, pickable vocabulary → rendered as chip toggles. The
 * remaining two (`region`, `industry`) are open coarse tags entered as chips.
 */
export const CLOSED_VOCAB: Partial<
  Record<TargetingDimension, readonly string[]>
> = {
  work_mode: WORK_MODE_VALUES,
  student_segment: STUDENT_SEGMENT_VALUES,
  language: LANGUAGE_VALUES,
  role_family: ROLE_FAMILY_VALUES,
};

/** True for the four fixed-vocab dimensions (chip toggles). */
export function isClosedVocabDimension(dim: TargetingDimension): boolean {
  return dim in CLOSED_VOCAB;
}

/** True for the two open coarse-tag dimensions (`region`, `industry`). */
export function isTagDimension(dim: TargetingDimension): boolean {
  return !isClosedVocabDimension(dim);
}

const MAX_VALUES_PER_DIM = 20;
const MAX_TOKEN_LEN = 64;

/**
 * Normalize + clamp a dimension's raw values exactly like the backend:
 * lowercase + trim, cap token length, de-dupe, cap the count, and drop any value
 * outside a closed vocabulary. A backend-closed vocab is enforced; the open tag
 * dimensions keep whatever survives normalization.
 */
export function normalizeDimensionValues(
  dim: TargetingDimension,
  raw: readonly (string | null | undefined)[] | undefined,
): string[] {
  if (!raw) return [];
  const vocab = CLOSED_VOCAB[dim];
  const out: string[] = [];
  const seen = new Set<string>();
  for (const item of raw) {
    const token = item?.trim().toLowerCase();
    if (!token) continue;
    const clamped = token.slice(0, MAX_TOKEN_LEN);
    if (vocab && !vocab.includes(clamped)) continue;
    if (seen.has(clamped)) continue;
    seen.add(clamped);
    out.push(clamped);
    if (out.length >= MAX_VALUES_PER_DIM) break;
  }
  return out;
}

/**
 * Build a persisted-shape descriptor from the editor state. `automatic` (or any
 * non-`manual` mode) always emits empty dimensions (broad reach). In `manual`
 * mode ONLY the six allowlisted dimensions are iterated, so a non-allowlisted /
 * forbidden key in `dims` can never survive into the payload.
 */
export function buildTargetingDescriptor(
  mode: TargetingMode | string,
  dims: Partial<Record<string, readonly (string | null | undefined)[]>>,
): NormalizedTargeting {
  if (mode !== MODE_MANUAL) {
    return {
      mode: ALL_MODES.has(mode) ? (mode as TargetingMode) : MODE_AUTOMATIC,
      dimensions: {},
    };
  }
  const dimensions: Partial<Record<TargetingDimension, string[]>> = {};
  for (const dim of TARGETING_DIMENSIONS) {
    const values = normalizeDimensionValues(dim, dims[dim]);
    if (values.length > 0) dimensions[dim] = values;
  }
  return { mode: MODE_MANUAL, dimensions };
}

/**
 * Read a placement's stored descriptor into a safe editor shape. Tolerant of a
 * missing / legacy / hand-edited row: an unknown mode falls back to `automatic`
 * and only allowlisted dimension keys survive (default-deny).
 */
export function descriptorFromPlacement(
  placement: { targeting?: TargetingDescriptor | null } | null | undefined,
): NormalizedTargeting {
  const stored = placement?.targeting;
  const rawMode = typeof stored?.mode === "string" ? stored.mode : "";
  const mode: TargetingMode = ALL_MODES.has(rawMode)
    ? (rawMode as TargetingMode)
    : MODE_AUTOMATIC;

  const dimensions: Partial<Record<TargetingDimension, string[]>> = {};
  const rawDims = stored?.dimensions;
  if (mode !== MODE_AUTOMATIC && rawDims && typeof rawDims === "object") {
    for (const dim of TARGETING_DIMENSIONS) {
      const values = normalizeDimensionValues(
        dim,
        (rawDims as Record<string, unknown>)[dim] as string[] | undefined,
      );
      if (values.length > 0) dimensions[dim] = values;
    }
  }
  return { mode, dimensions };
}

/** Whether a descriptor is university-restricted (partner-immutable, read-only). */
export function isUniversityRestricted(
  descriptor: TargetingDescriptor | null | undefined,
): boolean {
  return descriptor?.mode === MODE_UNIVERSITY_RESTRICTED;
}

/** Total number of selected values across every dimension (for summaries). */
export function countTargetingValues(
  descriptor: TargetingDescriptor | null | undefined,
): number {
  const dims = descriptor?.dimensions;
  if (!dims) return 0;
  let total = 0;
  for (const dim of TARGETING_DIMENSIONS) {
    total += dims[dim]?.length ?? 0;
  }
  return total;
}

/** Dimensions that actually carry at least one value (for read-only display). */
export function activeDimensions(
  descriptor: TargetingDescriptor | null | undefined,
): TargetingDimension[] {
  const dims = descriptor?.dimensions;
  if (!dims) return [];
  return TARGETING_DIMENSIONS.filter((d) => (dims[d]?.length ?? 0) > 0);
}
