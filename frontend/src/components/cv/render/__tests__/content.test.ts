import { describe, expect, it } from "vitest";
import { buildDocumentContent, buildEditableContent } from "../content";
import type { CvSection } from "@/lib/api";

function section(partial: Partial<CvSection> & Pick<CvSection, "id" | "section_type">): CvSection {
  return {
    title: partial.section_type,
    sort_order: 0,
    content: {},
    is_visible: true,
    ...partial,
  };
}

describe("buildDocumentContent (read-only)", () => {
  it("drops empty and hidden sections", () => {
    const sections: CvSection[] = [
      section({ id: "h", section_type: "header", content: { name: "Ann" } }),
      section({ id: "s", section_type: "summary", sort_order: 10, content: {} }),
      section({
        id: "e",
        section_type: "experience",
        sort_order: 20,
        content: { entries: [{ heading: "Eng", highlights: ["did x"] }] },
      }),
      section({
        id: "hidden",
        section_type: "skills",
        sort_order: 30,
        is_visible: false,
        content: { items: [{ name: "TS" }] },
      }),
    ];
    const doc = buildDocumentContent(sections, "Fallback");
    expect(doc.header.name).toBe("Ann");
    // empty summary dropped, hidden skills dropped, only experience remains
    expect(doc.sections.map((s) => s.id)).toEqual(["e"]);
  });
});

describe("buildEditableContent", () => {
  it("keeps empty visible sections so they can be edited", () => {
    const sections: CvSection[] = [
      section({ id: "h", section_type: "header", content: {} }),
      section({ id: "s", section_type: "summary", sort_order: 10, content: {} }),
      section({ id: "exp", section_type: "experience", sort_order: 20, content: {} }),
      section({ id: "sk", section_type: "skills", sort_order: 30, content: { items: [] } }),
    ];
    const doc = buildEditableContent(sections, "Untitled");
    // header name falls back to title
    expect(doc.header.name).toBe("Untitled");
    // empty summary/experience/skills all preserved for editing
    expect(doc.sections.map((s) => s.id).sort()).toEqual(["exp", "s", "sk"]);
    const exp = doc.sections.find((s) => s.id === "exp");
    expect(exp?.kind).toBe("entries");
    const sk = doc.sections.find((s) => s.id === "sk");
    expect(sk?.kind).toBe("skills");
    const summary = doc.sections.find((s) => s.id === "s");
    expect(summary?.kind).toBe("text");
  });

  it("still drops hidden sections", () => {
    const sections: CvSection[] = [
      section({ id: "h", section_type: "header", content: {} }),
      section({
        id: "sk",
        section_type: "skills",
        is_visible: false,
        content: { items: [{ name: "TS" }] },
      }),
    ];
    const doc = buildEditableContent(sections, "X");
    expect(doc.sections).toHaveLength(0);
  });

  it("preserves empty skill items positionally when editing", () => {
    const sections: CvSection[] = [
      section({ id: "h", section_type: "header", content: {} }),
      section({
        id: "sk",
        section_type: "skills",
        content: { items: [{ name: "TS", level: 80 }, { name: "" }] },
      }),
    ];
    const doc = buildEditableContent(sections, "X");
    const sk = doc.sections[0];
    expect(sk?.kind === "skills" && sk.skills).toEqual([
      { name: "TS", level: 80 },
      { name: "", level: undefined },
    ]);
  });

  it("maps a divider marker section to a divider block", () => {
    const sections: CvSection[] = [
      section({ id: "h", section_type: "header", content: { name: "Ann" } }),
      section({ id: "d", section_type: "custom", sort_order: 10, content: { divider: true } }),
    ];
    // Read-only keeps the divider (it's presentation, not empty content).
    const doc = buildDocumentContent(sections, "X");
    const divider = doc.sections.find((s) => s.id === "d");
    expect(divider?.kind).toBe("divider");
  });

  it("reads a typed contact link (label/url/type)", () => {
    const sections: CvSection[] = [
      section({
        id: "h",
        section_type: "header",
        content: {
          name: "Ann",
          links: [{ label: "LinkedIn", url: "https://linkedin.com/in/ann", type: "linkedin" }],
        },
      }),
    ];
    const doc = buildDocumentContent(sections, "X");
    expect(doc.header.links[0]).toEqual({
      label: "LinkedIn",
      url: "https://linkedin.com/in/ann",
      type: "linkedin",
    });
  });
});
