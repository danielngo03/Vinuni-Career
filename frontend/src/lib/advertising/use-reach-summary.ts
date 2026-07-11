"use client";

import { useTranslations } from "next-intl";
import { useCampaignLabels } from "./campaign-labels";
import type { CampaignTargeting } from "@/lib/api";

/**
 * Plain-language reach summary for a campaign's COARSE targeting (spec §7.0).
 * Empty targeting reads as "broad reach"; otherwise it lists only the coarse,
 * privacy-safe dimensions the engine matches on — never GPS/exact location.
 */
export function useReachSummary() {
  const t = useTranslations("advertising.campaign.reach");
  const labels = useCampaignLabels();

  return (targeting: CampaignTargeting | null | undefined): string => {
    const loc = targeting?.locations ?? [];
    const maj = targeting?.majors ?? [];
    const car = targeting?.careers ?? [];
    const wm = targeting?.work_modes ?? [];
    const yr = targeting?.year_cohorts ?? [];

    if (!loc.length && !maj.length && !car.length && !wm.length && !yr.length) {
      return t("broad");
    }

    const parts: string[] = [];
    if (loc.length) parts.push(t("locations", { values: loc.map((v) => labels.location(v)).join(", ") }));
    if (maj.length) parts.push(t("majors", { values: maj.map((v) => labels.major(v)).join(", ") }));
    if (car.length) parts.push(t("careers", { values: car.map((v) => labels.career(v)).join(", ") }));
    if (wm.length) parts.push(t("workModes", { values: wm.map((v) => labels.workMode(v)).join(", ") }));
    if (yr.length) parts.push(t("yearCohorts", { values: yr.map((v) => labels.yearCohort(v)).join(", ") }));
    return `${t("prefix")} ${parts.join(" · ")}.`;
  };
}
