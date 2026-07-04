import { describe, expect, it } from "vitest";
import {
  buildOverrides,
  buildRows,
  classifyPath,
  initialDecisions,
  initialValues,
  pendingCount,
} from "../review-fields";
import type { IngestionReviewField } from "@/lib/api";

describe("classifyPath", () => {
  it("classifies contact fields with a stable i18n field key", () => {
    expect(classifyPath("contact.email")).toEqual({ group: "contact", fieldKey: "field_email" });
    expect(classifyPath("contact.name")).toEqual({ group: "contact", fieldKey: "field_full_name" });
    expect(classifyPath("contact.phone")).toEqual({ group: "contact", fieldKey: "field_phone" });
  });

  it("classifies section item fields by section, with no field key", () => {
    expect(classifyPath("skills[0].text")).toEqual({ group: "skills", fieldKey: null });
    expect(classifyPath("experience[3].text")).toEqual({ group: "experience", fieldKey: null });
  });

  it("falls back to 'other' for unrecognised paths", () => {
    expect(classifyPath("nonsense")).toEqual({ group: "other", fieldKey: null });
  });
});

function field(
  path: string,
  value: string,
  needsReview: boolean,
): IngestionReviewField {
  return { path, value, needs_review: needsReview };
}

describe("buildRows", () => {
  it("numbers list items within their group, 1-based", () => {
    const rows = buildRows([
      field("skills[0].text", "Python", false),
      field("skills[1].text", "SQL", false),
      field("contact.email", "a@b.com", true),
    ]);
    expect(rows[0]!.indexInGroup).toBe(1);
    expect(rows[1]!.indexInGroup).toBe(2);
    expect(rows[2]!.indexInGroup).toBeNull();
    expect(rows[2]!.fieldKey).toBe("field_email");
  });
});

describe("initialDecisions / initialValues", () => {
  it("defaults needs_review fields to pending and others to accepted", () => {
    const rows = buildRows([
      field("contact.email", "a@b.com", true),
      field("skills[0].text", "Python", false),
    ]);
    expect(initialDecisions(rows)).toEqual({
      "contact.email": "pending",
      "skills[0].text": "accepted",
    });
    expect(initialValues(rows)).toEqual({
      "contact.email": "a@b.com",
      "skills[0].text": "Python",
    });
  });
});

describe("pendingCount", () => {
  it("counts only undecided needs_review fields", () => {
    const rows = buildRows([
      field("contact.email", "a@b.com", true),
      field("contact.phone", "123", true),
      field("skills[0].text", "Python", false),
    ]);
    const decisions = { ...initialDecisions(rows), "contact.email": "accepted" as const };
    expect(pendingCount(rows, decisions)).toBe(1);
  });
});

describe("buildOverrides", () => {
  it("includes every needs_review field, decided or not, plus any edited field", () => {
    const rows = buildRows([
      field("contact.email", "typo@example.com", true),
      field("skills[0].text", "Python", false),
    ]);
    const values = { ...initialValues(rows), "contact.email": "fixed@example.com" };
    const decisions = { ...initialDecisions(rows), "contact.email": "accepted" as const };

    const overrides = buildOverrides(rows, values, decisions);

    expect(overrides).toEqual([
      { path: "contact.email", value: "fixed@example.com", accepted: true },
    ]);
  });

  it("marks a rejected field as accepted: false so it is excluded on import", () => {
    const rows = buildRows([field("contact.phone", "555", true)]);
    const values = initialValues(rows);
    const decisions = { "contact.phone": "rejected" as const };

    expect(buildOverrides(rows, values, decisions)).toEqual([
      { path: "contact.phone", value: "555", accepted: false },
    ]);
  });

  it("omits fields that were never flagged for review and never edited", () => {
    const rows = buildRows([field("skills[0].text", "Python", false)]);
    const values = initialValues(rows);
    const decisions = initialDecisions(rows);

    expect(buildOverrides(rows, values, decisions)).toEqual([]);
  });
});
