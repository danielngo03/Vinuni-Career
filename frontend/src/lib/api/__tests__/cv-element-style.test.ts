import { describe, expect, it } from "vitest";
import { patchElementStyle } from "@/lib/api/cv";

/**
 * `patchElementStyle` is the contextual text toolbar's merge helper: it folds a
 * single-key change into the CV's element-style map and returns the FULL next
 * map (the shape the canvas PATCH expects). It must be immutable and must drop
 * empty entries so an element resets cleanly to the theme default.
 */
describe("patchElementStyle", () => {
  it("adds a new element's style", () => {
    const next = patchElementStyle(undefined, "header.name", { weight: "bold" });
    expect(next).toEqual({ "header.name": { weight: "bold" } });
  });

  it("merges into an existing element without touching siblings", () => {
    const current = {
      "header.name": { weight: "bold" as const },
      "section.a.text": { italic: true },
    };
    const next = patchElementStyle(current, "header.name", { color: "#123456" });
    expect(next["header.name"]).toEqual({ weight: "bold", color: "#123456" });
    expect(next["section.a.text"]).toEqual({ italic: true });
  });

  it("clears a single field when patched with undefined", () => {
    const current = { "header.name": { weight: "bold" as const, italic: true } };
    const next = patchElementStyle(current, "header.name", { weight: undefined });
    expect(next["header.name"]).toEqual({ italic: true });
  });

  it("removes the entry entirely when the last field is cleared", () => {
    const current = { "header.name": { color: "#123456" } };
    const next = patchElementStyle(current, "header.name", { color: undefined });
    expect(next["header.name"]).toBeUndefined();
    expect(Object.keys(next)).toHaveLength(0);
  });

  it("treats an empty-string value as a reset", () => {
    const current = { "header.name": { color: "#123456", weight: "bold" as const } };
    const next = patchElementStyle(current, "header.name", { color: "" });
    expect(next["header.name"]).toEqual({ weight: "bold" });
  });

  it("does not mutate the input map", () => {
    const current = { "header.name": { weight: "bold" as const } };
    patchElementStyle(current, "header.name", { italic: true });
    expect(current["header.name"]).toEqual({ weight: "bold" });
  });
});
