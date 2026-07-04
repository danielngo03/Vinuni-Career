"use client";

import { useTranslations } from "next-intl";
import type {
  ContactVisibility,
  DegreeLevel,
  OpenToWorkType,
  ProfileEmploymentType,
  ProfileVisibility,
  SkillCategory,
} from "@/lib/api";

/**
 * Localized labels for the student-profile enums, sourced from i18n so option
 * text follows the active locale (the API also returns `*_label`, but selects
 * need every option labeled, including the not-yet-saved one).
 */
export function useProfileLabels() {
  const t = useTranslations("profile.enums");

  return {
    visibility: (v: ProfileVisibility | string) => t(`visibility.${v}`),
    contact: (v: ContactVisibility | string) => t(`contact.${v}`),
    openToWork: (v: OpenToWorkType | string) => t(`openToWork.${v}`),
    degree: (v: DegreeLevel | string) => t(`degree.${v}`),
    employment: (v: ProfileEmploymentType | string) => t(`employment.${v}`),
    skillCategory: (v: SkillCategory | string) => t(`skillCategory.${v}`),
    proficiency: (n: number) => t(`proficiency.${n}`),
  };
}
