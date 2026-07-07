"use client";

import { useTranslations } from "next-intl";
import type {
  ContactVisibility,
  DegreeLevel,
  OpenToWorkType,
  ProfileVisibility,
} from "@/lib/api";

/**
 * Localized labels for the student-profile enums, sourced from i18n so option
 * text follows the active locale (the API also returns `*_label`, but selects
 * need every option labeled, including the not-yet-saved one). `degree` and
 * `openToWork` remain in use by the partner talent-search filters.
 */
export function useProfileLabels() {
  const t = useTranslations("profile.enums");

  return {
    visibility: (v: ProfileVisibility | string) => t(`visibility.${v}`),
    contact: (v: ContactVisibility | string) => t(`contact.${v}`),
    openToWork: (v: OpenToWorkType | string) => t(`openToWork.${v}`),
    degree: (v: DegreeLevel | string) => t(`degree.${v}`),
  };
}
