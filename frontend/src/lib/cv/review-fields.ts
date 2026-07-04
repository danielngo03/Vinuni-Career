/**
 * Pure helpers for the CV ingestion review screen
 * (`docs/CV_INGESTION_EXTRACTION_SPEC.md` §2 "Review Screen").
 *
 * Extracted from `components/cv/import-steps/review-step.tsx` so the
 * path-classification / grouping / override-building rules are unit-testable
 * without a DOM. These are the rules that decide what gets sent to
 * `POST /cv-ingestions/{id}/import` — they must never invent a path the
 * ingestion did not emit, and must always include a decision for every
 * "needs review" field before import is considered ready.
 */

import type { IngestionReviewField } from "@/lib/api";

export type FieldDecision = "pending" | "accepted" | "rejected";

export interface FieldRow extends IngestionReviewField {
  group: string;
  /** i18n key for a contact field (e.g. `field_email`); null for list items. */
  fieldKey: string | null;
  /** 1-based position within its group, for list items only. */
  indexInGroup: number | null;
}

const CONTACT_FIELD_KEY: Record<string, string> = {
  name: "field_full_name",
  email: "field_email",
  phone: "field_phone",
};

/** Classify a `review_fields[].path` into a display group + optional i18n field key. */
export function classifyPath(path: string): { group: string; fieldKey: string | null } {
  const contact = /^contact\.(name|email|phone)$/.exec(path);
  if (contact) {
    return { group: "contact", fieldKey: CONTACT_FIELD_KEY[contact[1]!] ?? null };
  }
  const item = /^([a-z_]+)\[\d+\]\.text$/.exec(path);
  if (item) return { group: item[1]!, fieldKey: null };
  return { group: "other", fieldKey: null };
}

/** Group + number the backend's `review_fields` for display. */
export function buildRows(fields: IngestionReviewField[]): FieldRow[] {
  const counters: Record<string, number> = {};
  return fields.map((f) => {
    const { group, fieldKey } = classifyPath(f.path);
    let indexInGroup: number | null = null;
    if (!fieldKey) {
      counters[group] = (counters[group] ?? 0) + 1;
      indexInGroup = counters[group]!;
    }
    return { ...f, group, fieldKey, indexInGroup };
  });
}

/** Default per-field decision: fields the backend flagged need an explicit decision. */
export function initialDecisions(rows: FieldRow[]): Record<string, FieldDecision> {
  return Object.fromEntries(rows.map((r) => [r.path, r.needs_review ? "pending" : "accepted"]));
}

export function initialValues(rows: FieldRow[]): Record<string, string> {
  return Object.fromEntries(rows.map((r) => [r.path, r.value]));
}

/** Count of "needs review" fields the student has not yet confirmed or removed. */
export function pendingCount(
  rows: FieldRow[],
  decisions: Record<string, FieldDecision>,
): number {
  return rows.filter((r) => r.needs_review && decisions[r.path] === "pending").length;
}

/**
 * Build the `overrides` array for the import request: every "needs review"
 * field (so the backend's per-field confirmation gate is satisfied) plus any
 * field the student edited away from its extracted value. Fields the student
 * left untouched and that were not flagged for review are omitted entirely —
 * they import using the ingestion's own extracted value, unchanged.
 */
export function buildOverrides(
  rows: FieldRow[],
  values: Record<string, string>,
  decisions: Record<string, FieldDecision>,
): { path: string; value: string; accepted: boolean }[] {
  return rows
    .filter((r) => r.needs_review || values[r.path] !== r.value)
    .map((r) => ({
      path: r.path,
      value: values[r.path] ?? r.value,
      accepted: decisions[r.path] !== "rejected",
    }));
}
