/** CV renderer — the single source of visual truth for a CV document. */

export { CvDocument } from "./cv-document";
export type {
  CvDocumentProps,
  CvDocumentContent,
  CvDocumentEditing,
  CvDocHeader,
  CvDocLink,
  CvDocEntry,
  CvDocSkill,
  CvDocSection,
  CvDocumentPhoto,
} from "./cv-document";
export {
  parseEditPath,
  applyTextEdit,
  applyStructuralEdit,
  isEntrySection,
  sectionUsesSkillItems,
} from "./edit-path";
export type {
  ParsedEditPath,
  CvEdit,
  HeaderField,
  EntryField,
} from "./edit-path";
export {
  DEFAULT_THEME,
  FONT_STACK,
  fontStack,
  resolveTheme,
} from "./theme";
export type {
  CvTheme,
  PartialCvTheme,
  LayoutKind,
  FontKind,
  CvThemeLayout,
  CvThemePalette,
  CvThemeTypography,
  CvThemePhoto,
  CvThemeSectionStyle,
  CvThemeRegions,
} from "./theme";
export { themeForTemplate } from "./builtin-themes";
export { buildDocumentContent, buildEditableContent } from "./content";
export { SAMPLE_CV } from "./sample-cv";
export { iconForLink, CONTACT_FIELD_ICON } from "./link-icons";
