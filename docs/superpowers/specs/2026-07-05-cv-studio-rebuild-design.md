# CV Studio Rebuild — Design Spec

- Date: 2026-07-05
- Status: approved (architecture + 3 key decisions), phased build
- Owner decisions locked (this session):
  1. Admin authoring = **visual theme composer** (no file upload / no Photoshop / no raw JSON).
  2. PDF export = **print the same `<CvDocument/>` renderer** (headless Chromium); student = clean, partner = watermarked.
  3. Scope = **full rebuild across phases P1→P5**, verify each phase.

Related source-of-truth docs: `docs/CV_STUDIO_SPEC.md` (§"Visual Canvas Editor Contract"),
`docs/DATA_MODEL.md`, `docs/API_CONTRACTS.md`, `docs/SECURITY_PRIVACY.md`, `.claude/rules/backend.md`,
`.claude/rules/frontend.md`, `CLAUDE.md` (CV Studio rules).

---

## 1. Goal

Turn CV Studio's template flow into a real, Canva-like experience: diverse, colorful,
multi-layout templates a student picks and **edits directly on the page**, with a
profile photo, live restyle (template/palette/font), and AI chat that fills the CV —
all rendering identically on screen and in the exported PDF.

### Non-goals (this rebuild)

- Free-form absolute-position canvas (drag any element anywhere). We do
  **structured layout** (sections bound to template regions), which is what real CV
  builders do and what keeps content ATS-safe, reflowable, and AI-fillable.
- DOCX export (PDF only in v1, per `CV_STUDIO_SPEC.md`).
- Changing the uploaded-CV flow (upload → name → done, read-only) — untouched.

---

## 2. Current-state problems (grounded)

1. **Templates carry no design.** `CvTemplate.layout_schema` only holds
   `section_order` + a font hint (`sans`/`serif`) + page count. The 7 seeded
   templates differ only in section order. No colors, no columns, no visual identity.
   → every CV looks identical regardless of template.
2. **No single source of visual truth.** Two renderers, both ignore the template and
   disagree with each other:
   - Frontend `cv-canvas-editor.tsx`: single-column, monochrome, white/black + brand
     underline. Never reads `layout_schema`.
   - Backend `pdf_render.py` (fpdf2): plain bullet list; also only reads
     `content.items`, so it **drops all structured `entries`** (experience/education).
3. **Editor is form-first.** Center column = section forms; canvas is only a preview.
   Not "edit on the template."
4. **Admin authoring is raw JSON.** `POST/PATCH /admin/cv-templates` takes a raw
   `layout_schema` dict; no live preview, no versioning, no publish/archive.

---

## 3. Target architecture — one renderer, template = theme (data)

```
CV content (structured)              Template theme (data, versioned)
  contact { name, headline,            layout   { kind, columns, sidebar_side, width }
            email, phone, links,       palette  { primary, accent, sidebarBg,
            location, photo }                     sidebarText, text, muted, rule }
  sections [                           typography { headingFont, bodyFont, scale }
    experience → entries[]             photo    { show, shape, position }
    education  → entries[]             sectionStyle { heading: rule|band|caps, gap }
    skills     → items[]{name,level}   density  { comfortable | compact }
    summary/…  → items[]{text}         regions  { main:[...types], sidebar:[...types] }
  ]                                    order    [ section_type, ... ]
                    \                 /
                     →  <CvDocument content theme scale/> →  pixel-accurate A4
```

**`<CvDocument/>` is the only thing that draws a CV.** It is used by:

- the student **canvas editor** (the editing surface itself),
- the **live preview**,
- **template gallery thumbnails** (render with realistic sample content at small scale — always accurate, no stored crop),
- the **admin composer** preview,
- the **`/print/cv/[versionId]`** route that the headless renderer prints to PDF.

This kills the fpdf2 divergence and satisfies `CV_STUDIO_SPEC.md`: "Export preview uses
the same render pipeline as generated PDF."

### Content binding

Structured section data already exists (from the extraction rebuild): entry sections
`{entries:[{heading, subheading, timeframe, location, note, highlights[]}]}`,
`skills {items:[{name, level 0-100}]}`, text sections `{items:[{text}]}`, and contact
with `headline`. The renderer maps each `section_type` into the template's `regions`
(sidebar vs main) and renders per `sectionStyle`. Skills with a numeric `level` render
as bars/dots in sidebar layouts, as chips in header layouts, as comma text in ATS
layouts — driven by theme, not by content.

---

## 4. Data model changes

Backend-owned, versioned (per `.claude/rules/backend.md`: templates need layout schema,
owner/version/status, publish/archive audit; CV writes versioned; snapshots immutable).

### 4.1 `cv_templates` (enrich + govern)

- Enrich the design payload (keep column name `layout_schema` for compat, but it now
  carries the full theme in §3: `layout`, `palette`, `typography`, `photo`,
  `sectionStyle`, `density`, `regions`, `order`). Old rows upgraded by a data migration
  that maps `{section_order, typography.font}` → a default theme.
- New columns:
  - `status`: `draft` | `published` | `archived` (default `published` for seeds).
  - `version`: int, current published version number.
  - `owner_org_id`: nullable FK (university-owned vs built-in/global).
  - `published_at`, `archived_at`: nullable.
- New table `cv_template_versions` (immutable published snapshots) so publishing a new
  version never breaks CVs already referencing an older one:
  `id, template_id, version_number, design_json, preview_image, created_by, created_at`.
- `CvProfile.template_version_id`: nullable FK — the exact template version a CV is
  bound to (so a later admin edit doesn't silently restyle a student's finished CV;
  they opt in to "update to latest").

### 4.2 `cv_profiles.canvas_json` → add `theme` + photo source

`canvas_json` gains a `theme` object of **student overrides layered on top of the
template** (Canva-like recolor without forking the template):

```json
{
  "theme": { "palette": { "accent": "#0F766E" }, "typography": { "bodyFont": "serif" } },
  "photo": { "source": "system_avatar" | "upload", "document_id": "…", "shape": "circle", "crop": {…} },
  "blocks": [ { "section_id": "…", "order": 3, "visible": true } ]
}
```

- `photo.source = "system_avatar"` → renderer resolves the student's
  `student_profiles.avatar_url` at render time (no copy needed; falls back gracefully
  if the student later removes it).
- `photo.source = "upload"` → existing `POST /cvs/{id}/photo` path (crop/shape).
- Content facts stay in `cv_sections.content_json`; the canvas never duplicates facts.

### 4.3 Snapshots / versions

`cv_versions.snapshot_json` already carries `canvas` + `sections`. Add
`template_version_id` + resolved `theme` to the snapshot so a restore (and the PDF
render of any historical version) reproduces the exact look.

---

## 5. Built-in template themes (diverse, shipped in P1)

Eight themes, all rendered by the one renderer (no per-template code):

| Key | Layout | Palette | Font | Photo | Best for |
|---|---|---|---|---|---|
| `classic_ats` | single column | ink on white, thin rules | serif head / sans body | no | ATS-safe, conservative |
| `modern_navy` | left sidebar | navy sidebar, white main | sans | yes (circle) | general, skills-forward |
| `modern_teal` | right sidebar | teal accent | sans | yes (rounded) | tech/product |
| `minimal_mono` | single column | lots of whitespace, hairline rules | sans | no | design-lite, clean |
| `bold_header` | header band + 2 col body | dark header band, accent headings | sans | yes (square) | experienced, impact |
| `elegant_serif` | 2 column | warm accent, serif | serif | yes (circle) | finance/consulting |
| `creative_twotone` | colored left rail | two-tone (rail + accent heads) | sans | yes | marketing/creative |
| `tech_chips` | single column | mono accents, skill chips | mono head / sans body | optional | engineering |

Palette is swappable per-CV, so 8 layouts × palettes ≈ Canva-level variety. VinUni red
stays reserved for brand/destructive per DESIGN.md; templates use their own palettes but
default set stays professional and accessible (WCAG AA contrast checked in the renderer).

---

## 6. Student editor — canvas-first (P2)

The A4 render **is** the editing surface.

- Inline editing: click a heading/bullet/date/contact line → edit in place (contentEditable), autosave (debounced) → section content, versioned.
- Section blocks: add / remove / hide / **drag-reorder** (keyboard-accessible move too).
- Restyle rail (Canva-like): switch template (live, content preserved where bindings match); change palette; change font; toggle/adjust density.
- Photo: **Upload** or **Use system avatar**; crop + shape.
- Inline validation: missing dates, overlong bullets, empty required sections, page-break/overflow warning (measured against A4).
- Undo/redo, autosave indicator, version history + restore.
- Responsive: desktop = canvas + restyle inspector; mobile = tabs (Sections | Edit | Preview | AI) with zoomable A4, no horizontal overflow.
- The old form-based section editor is retired as the primary surface (kept only as a
  fallback "list edit" affordance for accessibility / bulk edit).

---

## 7. AI chat fill (P3)

Keep the non-destructive contract (already correct): AI produces a diff → student
confirms → new version + audit. Improve reach:

- A chat/command surface in the editor: student types natural language
  ("điền kinh nghiệm từ CV cũ của tôi", "làm summary hợp Data Analyst", "đưa Projects lên trên Experience").
- Backend resolves target CV/version/section + allowed sources (uploaded extraction,
  confirmed profile facts, another CV, raw notes), calls the AI task, returns a
  **structured content patch** bound to the template.
- UI shows the change on the canvas + a compact diff; accept/edit/reject; accept →
  `cv_versions` row + audit. AI never invents facts (unverified → "Cần xác nhận").
- Tools reused/aligned: `fill_cv_template_from_sources`, `draft_cv_from_sources`,
  `rewrite_cv_section`, `optimize_cv_for_job` (all `confirmation_required`).

---

## 8. Admin template composer (P4)

Replaces the raw-JSON admin screen. University admin (RBAC: `cv_templates` +
org_type=university, per current `template_admin_service`):

- Pick base **layout**, **palette**, **typography**, **photo** on/off, **section
  regions/order**, density → **live A4 preview via `<CvDocument/>`** with sample data.
- Save draft → **Publish** (creates immutable `cv_template_versions` row, bumps
  `version`, audit `cv_template.published`) → **Archive** (hides from students; existing
  CVs bound to a version keep working).
- Preview image generated by rendering the template (P5 headless), not a manual crop.
- No file upload anywhere in the flow.

API (align with `CV_STUDIO_SPEC.md` §7): `POST/PATCH /admin/cv-templates`,
`POST /admin/cv-templates/{id}/publish`, `.../archive`, `.../preview`.

---

## 9. PDF export — unified (P5)

- New Next.js print route `/print/cv/[versionId]` renders `<CvDocument/>` from a version
  snapshot with `@page`/print CSS (exact A4).
- Server render worker (headless Chromium via **Playwright — new dependency**, since
  only `fpdf2` is installed today) prints that route to PDF. Student self-download =
  clean; partner download = watermark overlay (`SECURITY_PRIVACY.md`), audited via
  `signed_file_accesses`.
- `fpdf2` path removed once parity is verified (interim: keep as labeled fallback).
- Dependency note / tradeoff: Playwright + a Chromium binary is heavier than the
  "lightweight, no-Docker" default; justified because the owner chose exact
  canvas↔PDF parity. Runs in the export worker only (not request path).

---

## 10. Phases & acceptance gates

Each phase ends green (ruff+mypy / tsc+eslint+build) with tests, and is browser-verified
before the next starts.

- **P1 — Template design foundation + renderer.**
  Backend: enrich `layout_schema` theme, add `status`/`version`/versions table + migration
  (upgrade+downgrade) + data migration for old templates; seed 8 themes. Frontend: build
  `<CvDocument/>` renderer + theme types; template gallery shows real live thumbnails.
  Gate: gallery shows 8 visually distinct templates; a CV detail renders through the new
  renderer; content `entries`/`skills(level)` bind correctly; tests for theme
  resolution + binding.
- **P2 — Canvas-first editor + photo (upload/system avatar).**
  Gate: student edits inline on the A4, reorders sections, switches template/palette/font
  live, adds photo from upload or system avatar, autosave+version+undo; mobile tabs; a11y.
- **P3 — AI chat fill.**
  Gate: natural-language fill/tailor → diff → confirm → version+audit; no fact invention;
  AI-unavailable/credit states; adversarial + confirmation tests.
- **P4 — Admin template composer.**
  Gate: admin composes → live preview → publish (versioned) → archive; RBAC + audit;
  existing student CVs unaffected by a new version.
- **P5 — Unified PDF export.**
  Gate: `/print/cv` route parity; headless export worker; watermark for partner; snapshot
  immutability; export queued/running/ready/failed states.

---

## 11. Testing (per `docs/TEST_STRATEGY.md` + backend rules)

- Renderer binding: entries/skills(level)/contact/photo across all 8 layouts;
  empty/overflow/missing-date; palette override; template switch preserves content.
- Backend: template versioning (publish/archive immutability), theme migration
  upgrade+downgrade, RBAC (student vs admin vs cross-owner), audit on every write,
  quota still enforced, snapshot immutability after edits.
- AI: diff-not-mutation, fact-confirmation required, AI-unavailable, credits only on
  success, no provider/model leakage.
- PDF: parity vs canvas, watermark on partner path, signed-access audit, version
  render reproducibility.
- Frontend: canvas inline edit, keyboard reorder, mobile tabs no-overflow, a11y for
  diff/gallery/inspector.

---

## 12. Risks / open questions

- **Playwright dependency (P5)** — heavier runtime; isolated to export worker. Acceptable
  per owner's parity choice; revisit if deploy target forbids Chromium.
- **Template-version binding vs "always latest"** — default: a CV binds to the version it
  was created/edited with; admin republish does not silently restyle finished CVs;
  student can opt into "update to latest template." (Confirm during P4.)
- **Contrast/accessibility of colorful palettes** — renderer enforces AA contrast on text
  regions; palettes chosen to pass. Sponsored/brand color rules unaffected.
- **Scope size** — 5 phases is multi-session; each is independently shippable and verified.
