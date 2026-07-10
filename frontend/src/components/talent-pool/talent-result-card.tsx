"use client";

import { useTranslations } from "next-intl";
import { ArrowRight, Check, MapPin, Sparkles } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Card, StatusChip, type ChipTone } from "@/components/kit";
import type { MatchTier, TalentMatch } from "@/lib/api";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return (parts[0]![0]! + parts[parts.length - 1]![0]!).toUpperCase();
}

/**
 * Match-tier → data-viz tone. A colorblind-safe descending ramp
 * (emerald → teal → amber → neutral). Deliberately NO purple/violet and NO
 * rose/red: none of these tiers is a "bad" state, so red would mislead.
 */
const TIER_TONE: Record<MatchTier, ChipTone> = {
  excellent: "emerald",
  strong: "teal",
  moderate: "amber",
  exploratory: "neutral",
};

function MatchTierChip({ tier }: { tier: MatchTier }) {
  const t = useTranslations("talentPool");
  const LABEL: Record<MatchTier, string> = {
    excellent: t("tierExcellent"),
    strong: t("tierStrong"),
    moderate: t("tierModerate"),
    exploratory: t("tierExploratory"),
  };
  return (
    <StatusChip tone={TIER_TONE[tier]} dot size="sm">
      {LABEL[tier]}
    </StatusChip>
  );
}

/** The card body — shared between the linked and non-linked (no-detail) variants. */
function CardBody({ match, interactive }: { match: TalentMatch; interactive: boolean }) {
  const t = useTranslations("talentPool");
  const location = [match.location_city, match.location_country].filter(Boolean).join(", ");

  return (
    <Card interactive={interactive} className="flex h-full flex-col gap-3 p-4">
      {/* Identity + tier */}
      <div className="flex items-start gap-3">
        <Avatar size="lg" className="size-11 ring-1 ring-border">
          {match.avatar_url && <AvatarImage src={match.avatar_url} alt="" />}
          <AvatarFallback className="bg-[var(--viz-indigo-soft)] font-semibold text-[var(--viz-indigo)]">
            {initials(match.display_name)}
          </AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1">
          <span
            className={
              "type-h3 block truncate font-semibold text-foreground" +
              (interactive ? " group-hover:text-[var(--brand-primary)]" : "")
            }
          >
            {match.display_name}
          </span>
          <span className="mt-1 flex items-center gap-1.5 text-[0.8125rem] text-muted-foreground">
            <MapPin aria-hidden className="size-3.5 shrink-0" strokeWidth={1.8} />
            <span className="truncate">{location || t("locationUnknown")}</span>
          </span>
        </div>
        <MatchTierChip tier={match.match_tier} />
      </div>

      {/* Matched skills */}
      {match.matched_skills.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {match.matched_skills.slice(0, 8).map((skill) => (
            <StatusChip key={skill} tone="indigo" size="sm">
              {skill}
            </StatusChip>
          ))}
        </div>
      )}

      {/* Human-readable reasons — no score, ever. */}
      {match.match_reasons.length > 0 && (
        <div className="mt-auto border-t border-border pt-3">
          <p className="mb-1.5 flex items-center gap-1.5 type-caption font-semibold uppercase tracking-wide text-muted-foreground">
            <Sparkles aria-hidden className="size-3.5" strokeWidth={1.8} />
            {t("reasonsLabel")}
          </p>
          <ul className="space-y-1">
            {match.match_reasons.slice(0, 3).map((reason, i) => (
              <li key={i} className="flex items-start gap-1.5 text-[0.8125rem] text-foreground">
                <Check
                  aria-hidden
                  className="mt-0.5 size-3.5 shrink-0 text-[var(--content-success)]"
                  strokeWidth={2.2}
                />
                <span className="min-w-0">{reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Footer affordance (only when a detail route exists) */}
      {interactive && (
        <span className="flex items-center gap-1 type-small font-medium text-muted-foreground transition-colors group-hover:text-[var(--brand-primary)]">
          {t("openProfile")}
          <ArrowRight aria-hidden className="size-3.5" strokeWidth={2} />
        </span>
      )}
    </Card>
  );
}

/**
 * A single ranked candidate. Links to the RBAC-gated profile detail when the
 * backend resolved a `profile_id`; otherwise renders a non-interactive card so we
 * never ship a dead link (owner rule: no dead links, honest permission surface).
 */
export function TalentResultCard({ match }: { match: TalentMatch }) {
  if (!match.profile_id) {
    return <CardBody match={match} interactive={false} />;
  }
  return (
    <Link
      href={`/partner/talent/${match.profile_id}`}
      className="group block rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
    >
      <CardBody match={match} interactive />
    </Link>
  );
}
