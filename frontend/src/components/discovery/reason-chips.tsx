"use client";

import { useTranslations } from "next-intl";
import {
  Target,
  MagnifyingGlass,
  MapPin,
  Briefcase,
  Buildings,
  SealCheck,
  Timer,
  TrendUp,
  Clock,
  Wrench,
  Sparkle,
  Heart,
} from "@phosphor-icons/react";
import { useJobLabels } from "@/lib/jobs/labels";
import { cn } from "@/lib/utils";
import type { ReasonCode, RecoSource } from "@/lib/api";

/**
 * Render user-safe recommendation reason codes as localized chips. Each chip
 * pairs an icon with text so meaning is never carried by color alone (WCAG).
 * `cv_fit` shows a 0-100 PRODUCT fit score — never "AI confidence". Unknown
 * codes are skipped. `skill_match` expands into one chip per skill (capped).
 */
export function ReasonChips({
  reasons,
  max = 3,
  className,
}: {
  reasons: ReasonCode[];
  max?: number;
  className?: string;
}) {
  const td = useTranslations("discovery.reason");
  const labels = useJobLabels();

  const chips = buildChips(reasons, td, labels.employmentType).slice(0, max);
  if (chips.length === 0) return null;

  return (
    <ul className={cn("flex flex-wrap gap-1.5", className)}>
      {chips.map((chip) => (
        <li
          key={chip.key}
          className={cn(
            "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium",
            chip.tone === "fit"
              ? "border-[var(--teal-500)]/40 bg-[var(--teal-50)] text-[var(--teal-600)]"
              : "border-white/60 bg-white/75 text-[var(--text-secondary)] backdrop-blur-sm",
          )}
        >
          <chip.icon aria-hidden weight="bold" className="size-3.5 shrink-0" />
          <span>{chip.label}</span>
        </li>
      ))}
    </ul>
  );
}

type Chip = {
  key: string;
  label: string;
  icon: React.ElementType;
  tone: "fit" | "neutral";
};

function buildChips(
  reasons: ReasonCode[],
  td: (key: string, values?: Record<string, string | number>) => string,
  employmentLabel: (code: string) => string,
): Chip[] {
  const out: Chip[] = [];
  for (let i = 0; i < reasons.length; i += 1) {
    const r = reasons[i];
    if (!r) continue;
    const idx = `${r.code}-${i}`;
    switch (r.code) {
      case "cv_fit":
        out.push({
          key: idx,
          icon: Target,
          tone: "fit",
          label: td("cv_fit", {
            cv_title: String((r as { cv_title?: string }).cv_title ?? ""),
            score: Number((r as { score?: number }).score ?? 0),
          }),
        });
        break;
      case "matches_search":
        out.push({
          key: idx,
          icon: MagnifyingGlass,
          tone: "neutral",
          label: td("matches_search", {
            term: String((r as { term?: string }).term ?? ""),
          }),
        });
        break;
      case "preferred_job_type":
        out.push({
          key: idx,
          icon: Briefcase,
          tone: "neutral",
          label: td("preferred_job_type", {
            value: employmentLabel(String((r as { value?: string }).value ?? "")),
          }),
        });
        break;
      case "preferred_location":
        out.push({
          key: idx,
          icon: MapPin,
          tone: "neutral",
          label: td("preferred_location", {
            value: String((r as { value?: string }).value ?? ""),
          }),
        });
        break;
      case "preferred_field":
        out.push({
          key: idx,
          icon: Target,
          tone: "neutral",
          label: td("preferred_field", {
            value: String((r as { value?: string }).value ?? ""),
          }),
        });
        break;
      case "similar_industry":
        out.push({
          key: idx,
          icon: Buildings,
          tone: "neutral",
          label: td("similar_industry", {
            value: String((r as { value?: string }).value ?? ""),
          }),
        });
        break;
      case "similar_role":
        out.push({ key: idx, icon: Sparkle, tone: "neutral", label: td("similar_role") });
        break;
      case "skill_match": {
        const skills = ((r as { skills?: string[] }).skills ?? []).slice(0, 3);
        if (skills.length === 0) {
          out.push({ key: idx, icon: Wrench, tone: "neutral", label: td("skill_match_generic") });
        } else {
          for (let s = 0; s < skills.length; s += 1) {
            const skill = skills[s];
            if (!skill) continue;
            out.push({
              key: `${idx}-${s}`,
              icon: Wrench,
              tone: "neutral",
              label: skill,
            });
          }
        }
        break;
      }
      case "saved_affinity":
        out.push({ key: idx, icon: Heart, tone: "neutral", label: td("saved_affinity") });
        break;
      case "verified_employer":
        out.push({ key: idx, icon: SealCheck, tone: "neutral", label: td("verified_employer") });
        break;
      case "deadline_soon":
        out.push({
          key: idx,
          icon: Timer,
          tone: "neutral",
          label: td("deadline_soon", {
            days: Number((r as { days?: number }).days ?? 0),
          }),
        });
        break;
      case "popular":
        out.push({ key: idx, icon: TrendUp, tone: "neutral", label: td("popular") });
        break;
      case "recent":
        out.push({ key: idx, icon: Clock, tone: "neutral", label: td("recent") });
        break;
      default:
        // Unknown future code — skip rather than expose a raw code.
        break;
    }
  }
  return out;
}

/**
 * Small pill that labels the inventory class of a recommended item. Sponsored
 * inventory is NOT labelled here — it uses the non-removable `SponsoredLabel`
 * disclosure instead. Returns null for organic-but-unlabelled sources.
 */
export function SourceBadge({ source }: { source: RecoSource }) {
  const td = useTranslations("discovery.source");
  if (source === "sponsored") return null;

  const map: Record<
    Exclude<RecoSource, "sponsored">,
    { label: string; cls: string } | null
  > = {
    recommended: {
      label: td("recommended"),
      cls: "border-[var(--brand-primary)]/30 bg-[var(--blue-50)] text-[var(--brand-primary)]",
    },
    curated: {
      label: td("curated"),
      cls: "border-[var(--teal-500)]/40 bg-[var(--teal-50)] text-[var(--teal-600)]",
    },
    recent: {
      label: td("recent"),
      cls: "border-white/60 bg-white/75 text-[var(--text-muted)] backdrop-blur-sm",
    },
    popular: {
      label: td("popular"),
      cls: "border-white/60 bg-white/75 text-[var(--text-muted)] backdrop-blur-sm",
    },
  };
  const entry = map[source];
  if (!entry) return null;

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[0.65rem] font-bold uppercase tracking-wide",
        entry.cls,
      )}
    >
      {entry.label}
    </span>
  );
}

/**
 * Product fit score pill (0-100). This is a deterministic product score, never a
 * model/AI confidence; the label intentionally says "fit", not "confidence".
 */
export function FitScore({ score, className }: { score: number; className?: string }) {
  const td = useTranslations("discovery");
  const clamped = Math.max(0, Math.min(100, Math.round(score)));
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border border-[var(--teal-500)]/40 bg-[var(--teal-50)] px-2 py-0.5 text-xs font-bold tabular-nums text-[var(--teal-600)]",
        className,
      )}
      title={td("fitScoreHint")}
    >
      <Target aria-hidden weight="bold" className="size-3.5" />
      {td("fitScoreValue", { score: clamped })}
    </span>
  );
}
