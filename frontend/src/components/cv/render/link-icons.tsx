/**
 * Contact-link → icon mapping for the CV document header (design spec §1
 * "Contact icons"). A header link carries an optional `type`
 * (`email|phone|website|linkedin|github|facebook|twitter|instagram|custom`); the
 * renderer draws the matching phosphor glyph before the label. Icons are
 * monochrome-consistent — they inherit the CURRENT theme colour via
 * `currentColor` (ink / muted / accent), never a per-brand rainbow colour.
 *
 * `custom`/unknown types and links with no `type` fall back to a generic link
 * glyph so every contact line item still reads as a link. Email / phone /
 * location (which are dedicated header fields, not links) map through
 * {@link CONTACT_FIELD_ICON}.
 */

import {
  EnvelopeSimple,
  FacebookLogo,
  GithubLogo,
  Globe,
  InstagramLogo,
  LinkSimple,
  LinkedinLogo,
  MapPin,
  Phone,
  TwitterLogo,
  type Icon,
} from "@phosphor-icons/react";
import type { CvLinkType } from "@/lib/api";

/** URL-prefix heuristics used to infer a link `type` when none is stored. */
const HOST_HINTS: Array<[RegExp, CvLinkType]> = [
  [/linkedin\.com/i, "linkedin"],
  [/github\.com/i, "github"],
  [/facebook\.com|fb\.com/i, "facebook"],
  [/twitter\.com|x\.com/i, "twitter"],
  [/instagram\.com/i, "instagram"],
  [/^mailto:/i, "email"],
  [/^tel:/i, "phone"],
];

/** Map a typed contact link to its phosphor icon. */
const LINK_TYPE_ICON: Record<CvLinkType, Icon> = {
  email: EnvelopeSimple,
  phone: Phone,
  website: Globe,
  linkedin: LinkedinLogo,
  github: GithubLogo,
  facebook: FacebookLogo,
  twitter: TwitterLogo,
  instagram: InstagramLogo,
  custom: LinkSimple,
};

/** Icons for the dedicated header contact fields (email / phone / location). */
export const CONTACT_FIELD_ICON = {
  email: EnvelopeSimple,
  phone: Phone,
  location: MapPin,
} as const;

/**
 * Resolve the icon for a header link. Prefers the explicit `type`; when it is
 * missing/`custom`, sniffs the URL host to pick a sensible glyph, else a
 * generic link icon.
 */
export function iconForLink(type: string | undefined, url?: string): Icon {
  if (type && type !== "custom" && type in LINK_TYPE_ICON) {
    return LINK_TYPE_ICON[type as CvLinkType];
  }
  if (url) {
    for (const [re, hinted] of HOST_HINTS) {
      if (re.test(url)) return LINK_TYPE_ICON[hinted];
    }
  }
  return LINK_TYPE_ICON.custom;
}
