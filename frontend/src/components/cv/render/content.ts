/**
 * Normalise a CV detail (`CvSection[]` from the API) into the renderer's
 * {@link CvDocumentContent} shape. This is the single place that understands the
 * loosely-typed backend `content` blob, so `cv-document.tsx` only ever deals
 * with clean, discriminated section models.
 *
 * Binding rules (see `docs/superpowers/specs/2026-07-05-cv-studio-rebuild-design.md`):
 * - the `header` section becomes the document header (falls back to `cv.title`);
 * - entry sections → `{ entries: [...] }`;
 * - skills → `{ skills: [{name, level?}] }`;
 * - languages → `{ languages: [...] }`;
 * - text sections (summary/interests) → `{ text }` or a short bullet list.
 */

import type { CvSection, CvSectionContent } from "@/lib/api";
import type {
  CvDocumentContent,
  CvDocEntry,
  CvDocHeader,
  CvDocLink,
  CvDocSection,
  CvDocSkill,
} from "./cv-document";

/** Section types rendered as a single free-text paragraph / short list. */
const TEXT_TYPES = new Set(["summary", "objective", "profile", "about", "interests"]);
/** Section types rendered as {name, level} lists. */
const SKILL_TYPES = new Set(["skills"]);
const LANGUAGE_TYPES = new Set(["languages"]);

function str(v: unknown): string | undefined {
  return typeof v === "string" && v.trim().length > 0 ? v.trim() : undefined;
}

function num(v: unknown): number | undefined {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  return undefined;
}

function toStringArray(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v.map((x) => str(x)).filter((x): x is string => Boolean(x));
}

function readLinks(content: CvSectionContent): CvDocLink[] {
  const raw = content["links"];
  if (!Array.isArray(raw)) return [];
  const out: CvDocLink[] = [];
  for (const item of raw) {
    if (item && typeof item === "object") {
      const rec = item as Record<string, unknown>;
      const url = str(rec.url);
      const label = str(rec.label) ?? url;
      const type = str(rec.type);
      if (label) out.push({ label, url, type });
    }
  }
  return out;
}

/** Extract the document header from the `header` section (if present). */
function readHeader(section: CvSection, fallbackName: string): CvDocHeader {
  const c = section.content ?? {};
  return {
    name: str(c["name"]) ?? fallbackName,
    headline: str(c["headline"]),
    email: str(c["email"]),
    phone: str(c["phone"]),
    location: str(c["location"]),
    links: readLinks(c),
  };
}

/**
 * Read structured entries. In EDITABLE mode empty entries and empty highlights
 * are KEPT (positionally) so freshly-added rows have a visible, editable slot;
 * in read-only mode blank highlights are stripped for a clean document.
 */
function readEntries(content: CvSectionContent, editable = false): CvDocEntry[] {
  const raw = content["entries"];
  if (!Array.isArray(raw)) return [];
  const out: CvDocEntry[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const rec = item as Record<string, unknown>;
    const highlights = editable
      ? (Array.isArray(rec.highlights)
          ? rec.highlights.map((h) => (typeof h === "string" ? h : ""))
          : [])
      : toStringArray(rec.highlights);
    out.push({
      heading: str(rec.heading),
      subheading: str(rec.subheading),
      timeframe: str(rec.timeframe),
      location: str(rec.location),
      note: str(rec.note),
      highlights,
    });
  }
  return out;
}

/** Read {name, level?} skill items; keeps empty names when editing. */
function readSkills(content: CvSectionContent, editable = false): CvDocSkill[] {
  const raw = content["items"];
  if (!Array.isArray(raw)) return [];
  const out: CvDocSkill[] = [];
  for (const item of raw) {
    if (item && typeof item === "object") {
      const rec = item as Record<string, unknown>;
      const name = str(rec.name) ?? str(rec.text);
      if (name) out.push({ name, level: num(rec.level) });
      else if (editable) out.push({ name: "", level: num(rec.level) });
    }
  }
  return out;
}

/** Text sections keep `content.text`, else join `items[].text` into a list. */
function readTextItems(
  content: CvSectionContent,
  editable = false,
): { text?: string; items: string[] } {
  const text = str(content.text);
  const items = Array.isArray(content.items)
    ? content.items
        .map((it) => (typeof it?.text === "string" ? it.text : undefined))
        .filter((x): x is string => (editable ? x !== undefined : Boolean(x)))
    : [];
  return { text, items };
}

/** Section types whose canonical shape is structured `entries`. */
const ENTRY_TYPES = new Set([
  "experience",
  "education",
  "projects",
  "certifications",
  "awards",
  "activities",
  "publications",
]);

/**
 * Map one CV section into a discriminated renderer section.
 *
 * In READ-ONLY mode (`editable=false`) empty sections/entries are dropped so
 * the document stays clean. In EDITABLE mode nothing is dropped: empty sections
 * still render (so the student can type into them), empty entry/skill lists are
 * preserved, and the `kind` is inferred from the section_type when the content
 * carries no shape hint yet.
 */
function mapSection(section: CvSection, editable: boolean): CvDocSection | null {
  const type = section.section_type;
  const content = section.content ?? {};
  const hasEntries = Array.isArray(content["entries"]);
  const hasItems = Array.isArray(content["items"]);

  // A divider is a presentation-only spacer inserted from the Elements inspector
  // (`content.divider === true`). It carries no editable text and renders as a
  // themed hairline in both editable and read-only mode.
  if (content["divider"] === true) {
    return { ...baseSection(section), kind: "divider" };
  }

  if (SKILL_TYPES.has(type)) {
    const skills = readSkills(content, editable);
    if (skills.length === 0 && !editable) return null;
    return { ...baseSection(section), kind: "skills", skills };
  }

  if (LANGUAGE_TYPES.has(type)) {
    const languages = readSkills(content, editable); // same {name, level?} shape
    if (languages.length === 0 && !editable) return null;
    return { ...baseSection(section), kind: "languages", languages };
  }

  // Entry sections: detected by an `entries` array OR (when editing) by a known
  // entry section_type that has no content shape yet.
  if (hasEntries || (editable && ENTRY_TYPES.has(type) && !hasItems)) {
    const entries = readEntries(content, editable);
    if (entries.length === 0 && !editable) return null;
    return { ...baseSection(section), kind: "entries", entries };
  }

  if (TEXT_TYPES.has(type)) {
    const { text, items } = readTextItems(content, editable);
    if (!text && items.length === 0 && !editable) return null;
    // When editing an empty text section, seed an empty paragraph so the
    // student gets an editable line rather than a bare heading.
    if (editable && text === undefined && items.length === 0) {
      return { ...baseSection(section), kind: "text", text: "" };
    }
    return { ...baseSection(section), kind: "text", text, items };
  }

  // Fallback: a generic list section (older/custom sections storing items[].text).
  const { items } = readTextItems(content, editable);
  if (items.length === 0 && !editable) return null;
  if (editable && items.length === 0) {
    return { ...baseSection(section), kind: "text", text: "" };
  }
  return { ...baseSection(section), kind: "text", items };
}

function baseSection(section: CvSection): {
  id: string;
  section_type: string;
  title: string;
  is_visible: boolean;
  sort_order: number;
} {
  return {
    id: section.id,
    section_type: section.section_type,
    title: section.title,
    is_visible: section.is_visible,
    sort_order: section.sort_order,
  };
}

/**
 * Build the renderer content model from a CV detail. `title` is the CV title
 * (used as the header name fallback when there is no `header` section).
 *
 * READ-ONLY: hidden sections and empty sections/entries are dropped so the
 * rendered document (preview / thumbnail / PDF) stays clean.
 */
export function buildDocumentContent(
  sections: CvSection[],
  title: string,
): CvDocumentContent {
  const headerSection = sections.find((s) => s.section_type === "header");
  const header = headerSection
    ? readHeader(headerSection, title)
    : { name: title, links: [] as CvDocLink[] };

  const docSections: CvDocSection[] = [];
  for (const s of sections) {
    if (s.section_type === "header") continue;
    if (!s.is_visible) continue;
    const mapped = mapSection(s, false);
    if (mapped) docSections.push(mapped);
  }
  docSections.sort((a, b) => a.sort_order - b.sort_order);

  return { header, sections: docSections };
}

/**
 * Build the EDITABLE content model for the canvas editor. Unlike
 * {@link buildDocumentContent} this keeps hidden sections OUT (a hidden section
 * shouldn't render on the page) but keeps EMPTY visible sections/entries so the
 * student can type into them, and always exposes header contact fields so they
 * are editable even when blank. The header name still falls back to the CV
 * title so a fresh CV isn't nameless on the page.
 */
export function buildEditableContent(
  sections: CvSection[],
  title: string,
): CvDocumentContent {
  const headerSection = sections.find((s) => s.section_type === "header");
  const header = headerSection
    ? readHeader(headerSection, title)
    : { name: title, links: [] as CvDocLink[] };

  const docSections: CvDocSection[] = [];
  for (const s of sections) {
    if (s.section_type === "header") continue;
    if (!s.is_visible) continue;
    const mapped = mapSection(s, true);
    if (mapped) docSections.push(mapped);
  }
  docSections.sort((a, b) => a.sort_order - b.sort_order);

  return { header, sections: docSections };
}
