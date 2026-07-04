import type { CvSection, CvSectionContent } from "@/lib/api";

/**
 * Section editor mode. Summary-style sections edit a single rich text block;
 * everything else edits an ordered list of bullet items. Section content is a
 * free-form JSON object on the backend, so we infer mode from the existing
 * shape first, then fall back to the section_type default.
 */
export type SectionMode = "text" | "list";

/** Section types that default to a single free-text block. */
const TEXT_SECTION_TYPES: ReadonlySet<string> = new Set([
  "summary",
  "objective",
  "profile",
  "about",
]);

export function sectionMode(section: CvSection): SectionMode {
  const c = section.content ?? {};
  if (Array.isArray(c.items)) return "list";
  if (typeof c.text === "string") return "text";
  return TEXT_SECTION_TYPES.has(section.section_type) ? "text" : "list";
}

/** Extract the free-text value from a section (empty string when none). */
export function sectionText(content: CvSectionContent | undefined): string {
  if (!content) return "";
  return typeof content.text === "string" ? content.text : "";
}

/** Extract bullet item strings from a section. */
export function sectionItems(content: CvSectionContent | undefined): string[] {
  if (!content || !Array.isArray(content.items)) return [];
  return content.items.map((it) =>
    typeof it?.text === "string" ? it.text : "",
  );
}

/** Build the content JSON for a text-mode section. */
export function buildTextContent(text: string): CvSectionContent {
  return { text };
}

/** Build the content JSON for a list-mode section, dropping blank items. */
export function buildListContent(items: string[]): CvSectionContent {
  return {
    items: items
      .map((t) => t.trim())
      .filter((t) => t.length > 0)
      .map((text) => ({ text })),
  };
}

/** True when a section has no user content yet (drives guided empty states). */
export function isSectionEmpty(section: CvSection): boolean {
  if (sectionMode(section) === "text") {
    return sectionText(section.content).trim().length === 0;
  }
  return sectionItems(section.content).filter((t) => t.trim().length > 0).length === 0;
}

/** i18n key under `cv.sectionTypes.*` for a section_type (with safe fallback). */
export function sectionTypeKey(sectionType: string): string {
  return sectionType.replace(/[^a-z0-9_]/gi, "_");
}
