"use client";

import { useTranslations } from "next-intl";
import type { PlacementStatus, PlacementType } from "@/lib/api";
import type { StatusTone } from "@/components/ui";

/**
 * Localized enum labels for advertising placements. The backend already pairs
 * every enum code with a vi `*_label`; for vi/en parity we map the stable CODE
 * through next-intl and fall back to the server label (then the raw code) for any
 * unknown value. Raw enum codes are never shown to the user.
 */
export function useAdvertisingLabels() {
  const t = useTranslations("advertising.enums");

  const make =
    (group: string) =>
    (code: string | null | undefined, serverLabel?: string | null): string => {
      if (!code) return serverLabel || "—";
      const key = `${group}.${code}`;
      if (t.has(key)) return t(key);
      return serverLabel || code;
    };

  return {
    status: make("status"),
    placementType: make("placementType"),
    targetType: make("targetType"),
  };
}

/** Map a placement lifecycle status to a StatusBadge tone (never color alone). */
export const PLACEMENT_STATUS_TONE: Record<PlacementStatus, StatusTone> = {
  draft: "draft",
  pending_approval: "pending",
  approved: "info",
  active: "active",
  completed: "accepted",
  rejected: "rejected",
  cancelled: "closed",
};

/** Map a placement type to a StatusBadge tone for the inventory chip. */
export const PLACEMENT_TYPE_TONE: Record<PlacementType, StatusTone> = {
  sponsored: "info",
  featured: "featured",
  both: "verified",
};
