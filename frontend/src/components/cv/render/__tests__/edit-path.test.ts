import { describe, expect, it } from "vitest";
import {
  parseEditPath,
  applyTextEdit,
  applyStructuralEdit,
  type ParsedEditPath,
} from "../edit-path";
import type { CvSectionContent } from "@/lib/api";

describe("parseEditPath", () => {
  it("parses header field paths", () => {
    expect(parseEditPath("header.name")).toEqual({
      kind: "header.field",
      field: "name",
    });
    expect(parseEditPath("header.email")).toEqual({
      kind: "header.field",
      field: "email",
    });
  });

  it("parses header link paths", () => {
    expect(parseEditPath("header.links.2.label")).toEqual({
      kind: "header.link",
      index: 2,
      part: "label",
    });
    expect(parseEditPath("header.links.0.url")).toEqual({
      kind: "header.link",
      index: 0,
      part: "url",
    });
  });

  it("parses section text + item + entry paths", () => {
    expect(parseEditPath("section.s1.text")).toEqual({
      kind: "section.text",
      sectionId: "s1",
    });
    expect(parseEditPath("section.s1.items.3.name")).toEqual({
      kind: "section.item.name",
      sectionId: "s1",
      index: 3,
    });
    expect(parseEditPath("section.s1.entries.1.heading")).toEqual({
      kind: "section.entry.field",
      sectionId: "s1",
      index: 1,
      field: "heading",
    });
    expect(parseEditPath("section.s1.entries.0.highlights.2")).toEqual({
      kind: "section.entry.highlight",
      sectionId: "s1",
      entryIndex: 0,
      highlightIndex: 2,
    });
  });

  it("rejects malformed / unknown paths", () => {
    expect(parseEditPath("header.unknown")).toBeNull();
    expect(parseEditPath("header.links.x.label")).toBeNull();
    expect(parseEditPath("section")).toBeNull();
    expect(parseEditPath("section.s1.entries.1.badfield")).toBeNull();
    expect(parseEditPath("garbage")).toBeNull();
  });
});

describe("applyTextEdit", () => {
  it("sets a header field", () => {
    const c: CvSectionContent = { name: "Old" };
    const target = parseEditPath("header.name") as ParsedEditPath;
    expect(applyTextEdit(c, target, "New Name")).toEqual({ name: "New Name" });
  });

  it("normalises non-breaking spaces and trims trailing whitespace", () => {
    const target = parseEditPath("header.headline") as ParsedEditPath;
    const out = applyTextEdit({}, target, "Data Analyst  ");
    expect(out.headline).toBe("Data Analyst");
  });

  it("writes an entry highlight by index, padding gaps", () => {
    const target = parseEditPath("section.s1.entries.0.highlights.1") as ParsedEditPath;
    const out = applyTextEdit({ entries: [{ highlights: ["first"] }] }, target, "second");
    expect(out.entries).toEqual([{ highlights: ["first", "second"] }]);
  });

  it("writes a skill name by index", () => {
    const target = parseEditPath("section.s1.items.0.name") as ParsedEditPath;
    const out = applyTextEdit({ items: [{ name: "", level: 50 }] }, target, "React");
    expect(out.items).toEqual([{ name: "React", level: 50 }]);
  });
});

describe("applyStructuralEdit", () => {
  it("adds and removes an entry", () => {
    const base: CvSectionContent = { entries: [{ heading: "A", highlights: [] }] };
    const added = applyStructuralEdit(base, { kind: "add-entry", sectionId: "s1" });
    expect(added.entries).toHaveLength(2);
    const removed = applyStructuralEdit(added, {
      kind: "remove-entry",
      sectionId: "s1",
      index: 0,
    });
    expect(removed.entries).toHaveLength(1);
  });

  it("adds and removes a highlight on an entry", () => {
    const base: CvSectionContent = { entries: [{ highlights: ["one"] }] };
    const added = applyStructuralEdit(base, {
      kind: "add-highlight",
      sectionId: "s1",
      entryIndex: 0,
    });
    expect((added.entries as Array<{ highlights: string[] }>)[0]!.highlights).toEqual([
      "one",
      "",
    ]);
    const removed = applyStructuralEdit(added, {
      kind: "remove-highlight",
      sectionId: "s1",
      entryIndex: 0,
      highlightIndex: 0,
    });
    expect((removed.entries as Array<{ highlights: string[] }>)[0]!.highlights).toEqual([
      "",
    ]);
  });

  it("adds a name item for skill sections and a text item otherwise", () => {
    const skill = applyStructuralEdit({ items: [{ name: "TS" }] }, {
      kind: "add-item",
      sectionId: "s1",
    });
    expect(skill.items).toEqual([{ name: "TS" }, { name: "" }]);

    const text = applyStructuralEdit({ items: [{ text: "hi" }] }, {
      kind: "add-item",
      sectionId: "s1",
    });
    expect(text.items).toEqual([{ text: "hi" }, { text: "" }]);
  });

  it("clamps skill level to 0-100", () => {
    const out = applyStructuralEdit({ items: [{ name: "TS" }] }, {
      kind: "set-skill-level",
      sectionId: "s1",
      index: 0,
      level: 250,
    });
    expect((out.items as Array<{ level: number }>)[0]!.level).toBe(100);
  });

  it("adds and removes header links", () => {
    // A bare on-canvas add-link seeds a blank `custom` link (the renderer draws
    // a generic link icon until the student picks/edits it).
    const added = applyStructuralEdit({}, { kind: "add-link" });
    expect(added.links).toEqual([{ label: "", url: "", type: "custom" }]);
    const removed = applyStructuralEdit(added, { kind: "remove-link", index: 0 });
    expect(removed.links).toEqual([]);
  });

  it("adds a typed header link (Elements inspector)", () => {
    // The Elements inspector seeds a typed link so the renderer picks the icon.
    const added = applyStructuralEdit(
      {},
      { kind: "add-link", type: "linkedin", label: "LinkedIn" },
    );
    expect(added.links).toEqual([{ label: "LinkedIn", url: "", type: "linkedin" }]);
  });
});
