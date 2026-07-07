"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import {
  Article,
  ChartBar,
  FacebookLogo,
  GithubLogo,
  Globe,
  InstagramLogo,
  LinkSimple,
  LinkedinLogo,
  Minus,
  Plus,
  PuzzlePiece,
  TwitterLogo,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";
import type { CvLinkType } from "@/lib/api";

/**
 * The Elements inspector (design spec §3 "Phần tử / Elements") — the
 * CUSTOMIZATION surface. When a template's personal-info block lacks a
 * LinkedIn/GitHub/Facebook field, the student adds it here as a TYPED header
 * link (so the renderer draws the right icon). Also inserts custom fields,
 * dividers, skill bars, and new sections. Every insert flows through the same
 * structural-edit / add-section machinery the on-canvas affordances use, so it
 * persists + versions identically. Purely presentational.
 */

/** Typed social/contact links the student can add (icon + default label). */
const SOCIAL_LINKS: Array<{ type: CvLinkType; icon: typeof LinkedinLogo; labelKey: string; defaultLabel: string }> = [
  { type: "linkedin", icon: LinkedinLogo, labelKey: "linkedin", defaultLabel: "LinkedIn" },
  { type: "github", icon: GithubLogo, labelKey: "github", defaultLabel: "GitHub" },
  { type: "facebook", icon: FacebookLogo, labelKey: "facebook", defaultLabel: "Facebook" },
  { type: "twitter", icon: TwitterLogo, labelKey: "twitter", defaultLabel: "Twitter" },
  { type: "instagram", icon: InstagramLogo, labelKey: "instagram", defaultLabel: "Instagram" },
  { type: "website", icon: Globe, labelKey: "website", defaultLabel: "Website" },
  { type: "custom", icon: LinkSimple, labelKey: "customLink", defaultLabel: "" },
];

/** Section types offered by the "add section" picker. */
const SECTION_TYPES = [
  "experience",
  "education",
  "projects",
  "skills",
  "certifications",
  "awards",
  "languages",
  "activities",
  "summary",
  "custom",
] as const;

export function ElementsInspector({
  onAddLink,
  onAddSection,
  onAddDivider,
  onAddSkillBar,
  onAddCustomField,
  hasHeader,
  addingSection,
}: {
  /** Add a typed header link (LinkedIn/GitHub/…). */
  onAddLink: (link: { type: CvLinkType; label: string }) => void;
  /** Add a section of the chosen type. */
  onAddSection: (sectionType: string) => void;
  /** Add a presentation-only divider section. */
  onAddDivider: () => void;
  /** Add a skills section with a level bar. */
  onAddSkillBar: () => void;
  /** Add a free custom field/section the student names. */
  onAddCustomField: () => void;
  /** Whether the CV has a header section (link insert targets it). */
  hasHeader: boolean;
  addingSection: boolean;
}) {
  const t = useTranslations("cv.elements");
  const [sectionType, setSectionType] = useState<string>("experience");

  return (
    <section
      aria-label={t("title")}
      className="space-y-5 rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] p-4 shadow-[var(--shadow-sm)] backdrop-blur-md"
    >
      <div className="flex items-center gap-2">
        <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-primary shadow-sm">
          <PuzzlePiece aria-hidden weight="duotone" className="size-3.5 text-white" />
        </span>
        <h3 className="text-sm font-bold text-[var(--text-primary)]">{t("title")}</h3>
      </div>

      {/* ------------------------- Contact / social links ------------------ */}
      <div>
        <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
          {t("contactLinks")}
        </p>
        <p className="mb-2.5 text-xs leading-relaxed text-[var(--text-secondary)]">
          {t("contactLinksHint")}
        </p>
        <div className="grid grid-cols-2 gap-1.5">
          {SOCIAL_LINKS.map((link) => {
            const Icon = link.icon;
            const label = t(`links.${link.labelKey}`);
            return (
              <button
                key={link.type + link.labelKey}
                type="button"
                disabled={!hasHeader}
                onClick={() => onAddLink({ type: link.type, label: link.defaultLabel || label })}
                className={cn(
                  "flex items-center gap-2 rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] px-2.5 py-2 text-left text-xs font-medium text-[var(--text-primary)] outline-none transition-colors hover:border-[var(--brand-primary)]/50 hover:bg-[var(--glass-surface-heavy)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40 disabled:cursor-not-allowed disabled:opacity-45",
                )}
              >
                <Icon aria-hidden weight="regular" className="size-4 shrink-0 text-[var(--text-secondary)]" />
                <span className="min-w-0 flex-1 truncate">{label}</span>
                <Plus aria-hidden weight="bold" className="size-3 shrink-0 text-[var(--text-muted)]" />
              </button>
            );
          })}
        </div>
        {!hasHeader && (
          <p className="mt-1.5 text-[11px] leading-relaxed text-[var(--text-muted)]">
            {t("noHeaderHint")}
          </p>
        )}
      </div>

      {/* ------------------------------ Blocks ----------------------------- */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
          {t("blocks")}
        </p>
        <div className="grid grid-cols-3 gap-1.5">
          <InsertTile icon={ChartBar} label={t("skillBar")} onClick={onAddSkillBar} />
          <InsertTile icon={Article} label={t("customField")} onClick={onAddCustomField} />
          <InsertTile icon={Minus} label={t("divider")} onClick={onAddDivider} />
        </div>
      </div>

      {/* ---------------------------- Add section -------------------------- */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
          {t("addSection")}
        </p>
        <div className="flex gap-2">
          <label htmlFor="cv-add-section-type" className="sr-only">
            {t("sectionTypeLabel")}
          </label>
          <select
            id="cv-add-section-type"
            value={sectionType}
            onChange={(e) => setSectionType(e.target.value)}
            className="min-w-0 flex-1 rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none backdrop-blur-sm transition-colors focus:border-[var(--brand-primary)]/50 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
          >
            {SECTION_TYPES.map((type) => (
              <option key={type} value={type}>
                {t(`sectionTypes.${type}`)}
              </option>
            ))}
          </select>
          <Button
            variant="secondary"
            size="sm"
            loading={addingSection}
            onClick={() => onAddSection(sectionType)}
          >
            <Plus aria-hidden weight="bold" className="size-4" />
            {t("add")}
          </Button>
        </div>
      </div>
    </section>
  );
}

function InsertTile({
  icon: Icon,
  label,
  onClick,
}: {
  icon: typeof ChartBar;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex flex-col items-center gap-1.5 rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] px-2 py-2.5 text-center outline-none transition-colors hover:border-[var(--brand-primary)]/50 hover:bg-[var(--glass-surface-heavy)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
    >
      <Icon aria-hidden weight="duotone" className="size-5 text-[var(--text-secondary)]" />
      <span className="text-[11px] font-medium leading-tight text-[var(--text-primary)]">{label}</span>
    </button>
  );
}
