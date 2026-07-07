/**
 * The `data-edit-path` grammar for the editable `<CvDocument editable/>` surface
 * (design spec §6, P2). A path uniquely addresses one editable text field OR one
 * structural mutation target inside the CV content model, so the builder screen
 * can apply an inline edit to its working `sections` copy and autosave the
 * affected section — without the renderer ever owning CV state.
 *
 * ── Text-field paths (edited in place via contentEditable) ──
 *   header.name
 *   header.headline
 *   header.email
 *   header.phone
 *   header.location
 *   header.links.{i}.label
 *   header.links.{i}.url
 *   section.{sectionId}.entries.{i}.heading      (+ .subheading/.timeframe/.location/.note)
 *   section.{sectionId}.entries.{i}.highlights.{j}
 *   section.{sectionId}.items.{i}.text           (text/list sections)
 *   section.{sectionId}.items.{i}.name           (skills/languages)
 *   section.{sectionId}.text                     (summary paragraph)
 *
 * Structural changes (add/remove entry, add/remove highlight, add/remove skill,
 * set skill level) are applied by the same pure reducer through the {@link CvEdit}
 * union so every mutation flows through one place and stays autosave/version safe.
 */

import type { CvSection, CvSectionContent, CvSectionItem } from "@/lib/api";

/* ------------------------------- Path parsing ----------------------------- */

/** Which header field a `header.*` path targets. */
export type HeaderField = "name" | "headline" | "email" | "phone" | "location";
/** Which entry field an `...entries.{i}.<field>` path targets. */
export type EntryField =
  | "heading"
  | "subheading"
  | "timeframe"
  | "location"
  | "note";

export type ParsedEditPath =
  | { kind: "header.field"; field: HeaderField }
  | { kind: "header.link"; index: number; part: "label" | "url" }
  | { kind: "section.text"; sectionId: string }
  | { kind: "section.item.text"; sectionId: string; index: number }
  | { kind: "section.item.name"; sectionId: string; index: number }
  | { kind: "section.entry.field"; sectionId: string; index: number; field: EntryField }
  | {
      kind: "section.entry.highlight";
      sectionId: string;
      entryIndex: number;
      highlightIndex: number;
    };

const HEADER_FIELDS = new Set<HeaderField>([
  "name",
  "headline",
  "email",
  "phone",
  "location",
]);
const ENTRY_FIELDS = new Set<EntryField>([
  "heading",
  "subheading",
  "timeframe",
  "location",
  "note",
]);

/**
 * Parse a `data-edit-path` string into a typed target. Returns `null` for any
 * malformed/unknown path so callers can safely ignore stray commits.
 */
export function parseEditPath(path: string): ParsedEditPath | null {
  const parts = path.split(".");

  if (parts[0] === "header") {
    if (parts.length === 2 && HEADER_FIELDS.has(parts[1] as HeaderField)) {
      return { kind: "header.field", field: parts[1] as HeaderField };
    }
    if (
      parts.length === 4 &&
      parts[1] === "links" &&
      (parts[3] === "label" || parts[3] === "url")
    ) {
      const index = Number(parts[2]);
      if (Number.isInteger(index) && index >= 0) {
        return { kind: "header.link", index, part: parts[3] };
      }
    }
    return null;
  }

  if (parts[0] === "section" && parts[1]) {
    const sectionId = parts[1];
    // section.{id}.text
    if (parts.length === 3 && parts[2] === "text") {
      return { kind: "section.text", sectionId };
    }
    // section.{id}.items.{i}.text | .name
    if (
      parts.length === 5 &&
      parts[2] === "items" &&
      (parts[4] === "text" || parts[4] === "name")
    ) {
      const index = Number(parts[3]);
      if (Number.isInteger(index) && index >= 0) {
        return parts[4] === "text"
          ? { kind: "section.item.text", sectionId, index }
          : { kind: "section.item.name", sectionId, index };
      }
    }
    // section.{id}.entries.{i}.<field>
    if (
      parts.length === 5 &&
      parts[2] === "entries" &&
      ENTRY_FIELDS.has(parts[4] as EntryField)
    ) {
      const index = Number(parts[3]);
      if (Number.isInteger(index) && index >= 0) {
        return {
          kind: "section.entry.field",
          sectionId,
          index,
          field: parts[4] as EntryField,
        };
      }
    }
    // section.{id}.entries.{i}.highlights.{j}
    if (parts.length === 6 && parts[2] === "entries" && parts[4] === "highlights") {
      const entryIndex = Number(parts[3]);
      const highlightIndex = Number(parts[5]);
      if (
        Number.isInteger(entryIndex) &&
        entryIndex >= 0 &&
        Number.isInteger(highlightIndex) &&
        highlightIndex >= 0
      ) {
        return {
          kind: "section.entry.highlight",
          sectionId,
          entryIndex,
          highlightIndex,
        };
      }
    }
  }

  return null;
}

/* ---------------------------- Structural edits ---------------------------- */

/**
 * A structural CV mutation emitted by on-canvas affordances. `commit` (a text
 * edit) is handled separately by {@link applyTextEdit} since it's the hot path.
 */
export type CvEdit =
  | { kind: "add-entry"; sectionId: string }
  | { kind: "remove-entry"; sectionId: string; index: number }
  | { kind: "add-highlight"; sectionId: string; entryIndex: number }
  | { kind: "remove-highlight"; sectionId: string; entryIndex: number; highlightIndex: number }
  | { kind: "add-item"; sectionId: string }
  | { kind: "remove-item"; sectionId: string; index: number }
  | { kind: "set-skill-level"; sectionId: string; index: number; level: number }
  // `add-link` may seed a typed link (label/url/type) — used by the Elements
  // inspector to insert e.g. a LinkedIn/GitHub contact with the right icon. A
  // bare `add-link` (on-canvas "+") adds a blank custom link the student fills in.
  | { kind: "add-link"; label?: string; url?: string; type?: string }
  | { kind: "remove-link"; index: number };

/* --------------------------- Content read helpers ------------------------- */

interface RawEntry {
  heading?: string;
  subheading?: string;
  timeframe?: string;
  location?: string;
  note?: string;
  highlights?: string[];
  [k: string]: unknown;
}

function readEntries(content: CvSectionContent): RawEntry[] {
  return Array.isArray(content.entries)
    ? (content.entries as RawEntry[]).map((e) => ({ ...e }))
    : [];
}

function readItems(content: CvSectionContent): CvSectionItem[] {
  return Array.isArray(content.items)
    ? content.items.map((it) => ({ ...it }))
    : [];
}

function readLinks(
  content: CvSectionContent,
): Array<{ label?: string; url?: string; type?: string }> {
  const raw = content.links;
  return Array.isArray(raw)
    ? (raw as Array<{ label?: string; url?: string; type?: string }>).map((l) => ({ ...l }))
    : [];
}

/** True when a section stores structured `entries`. */
function isEntrySection(content: CvSectionContent): boolean {
  return Array.isArray(content.entries);
}

/* ---------------------------- Apply a text edit --------------------------- */

/**
 * Apply an inline text commit to a section's content, returning the new content
 * (or the same reference when nothing changed). Header commits are applied to
 * the header section's content; the caller resolves which section that is.
 */
export function applyTextEdit(
  content: CvSectionContent,
  target: ParsedEditPath,
  value: string,
): CvSectionContent {
  // contentEditable often inserts non-breaking spaces (U+00A0); normalise
  // them to regular spaces and trim trailing whitespace before storing.
  const v = value.replace(/\u00a0/g, " ").trimEnd();

  switch (target.kind) {
    case "header.field": {
      return { ...content, [target.field]: v };
    }
    case "header.link": {
      const links = readLinks(content);
      while (links.length <= target.index) links.push({});
      links[target.index] = { ...links[target.index], [target.part]: v };
      return { ...content, links };
    }
    case "section.text": {
      return { ...content, text: v };
    }
    case "section.item.text": {
      const items = readItems(content);
      while (items.length <= target.index) items.push({ text: "" });
      items[target.index] = { ...items[target.index], text: v };
      return { ...content, items };
    }
    case "section.item.name": {
      const items = readItems(content);
      while (items.length <= target.index) items.push({ name: "" });
      items[target.index] = { ...items[target.index], name: v };
      return { ...content, items };
    }
    case "section.entry.field": {
      const entries = readEntries(content);
      while (entries.length <= target.index) entries.push({ highlights: [] });
      entries[target.index] = { ...entries[target.index], [target.field]: v };
      return { ...content, entries };
    }
    case "section.entry.highlight": {
      const entries = readEntries(content);
      while (entries.length <= target.entryIndex) entries.push({ highlights: [] });
      const entry = entries[target.entryIndex]!;
      const highlights = Array.isArray(entry.highlights) ? [...entry.highlights] : [];
      while (highlights.length <= target.highlightIndex) highlights.push("");
      highlights[target.highlightIndex] = v;
      entries[target.entryIndex] = { ...entry, highlights };
      return { ...content, entries };
    }
    default:
      return content;
  }
}

/* -------------------------- Apply a structural edit ----------------------- */

/**
 * Apply a structural mutation to a section's content. Returns the new content;
 * `add-link`/`remove-link` operate on a header section's `links`.
 */
export function applyStructuralEdit(
  content: CvSectionContent,
  edit: CvEdit,
): CvSectionContent {
  switch (edit.kind) {
    case "add-entry": {
      const entries = readEntries(content);
      entries.push({ heading: "", highlights: [] });
      return { ...content, entries };
    }
    case "remove-entry": {
      const entries = readEntries(content).filter((_, i) => i !== edit.index);
      return { ...content, entries };
    }
    case "add-highlight": {
      const entries = readEntries(content);
      if (!entries[edit.entryIndex]) return content;
      const entry = entries[edit.entryIndex]!;
      const highlights = Array.isArray(entry.highlights) ? [...entry.highlights] : [];
      highlights.push("");
      entries[edit.entryIndex] = { ...entry, highlights };
      return { ...content, entries };
    }
    case "remove-highlight": {
      const entries = readEntries(content);
      if (!entries[edit.entryIndex]) return content;
      const entry = entries[edit.entryIndex]!;
      const highlights = (Array.isArray(entry.highlights) ? entry.highlights : []).filter(
        (_, j) => j !== edit.highlightIndex,
      );
      entries[edit.entryIndex] = { ...entry, highlights };
      return { ...content, entries };
    }
    case "add-item": {
      const items = readItems(content);
      // Skill/language items use `name`; text/list items use `text`. Infer from
      // the existing first item shape, defaulting to `text`.
      const useName = items.some((it) => typeof it.name === "string" && it.name !== undefined);
      items.push(useName ? { name: "" } : { text: "" });
      return { ...content, items };
    }
    case "remove-item": {
      const items = readItems(content).filter((_, i) => i !== edit.index);
      return { ...content, items };
    }
    case "set-skill-level": {
      const items = readItems(content);
      if (!items[edit.index]) return content;
      const level = Math.max(0, Math.min(100, Math.round(edit.level)));
      items[edit.index] = { ...items[edit.index], level };
      return { ...content, items };
    }
    case "add-link": {
      const links = readLinks(content);
      // Seed a typed link when the Elements inspector supplies one (LinkedIn /
      // GitHub / …), else a blank custom link for the on-canvas "+".
      links.push({
        label: edit.label ?? "",
        url: edit.url ?? "",
        type: edit.type ?? "custom",
      });
      return { ...content, links };
    }
    case "remove-link": {
      const links = readLinks(content).filter((_, i) => i !== edit.index);
      return { ...content, links };
    }
    default:
      return content;
  }
}

/** Whether an edit / structural op is a skill-name-carrying section. */
export function sectionUsesSkillItems(section: CvSection): boolean {
  return section.section_type === "skills" || section.section_type === "languages";
}

export { isEntrySection };
