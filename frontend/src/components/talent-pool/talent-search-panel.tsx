"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { Search, Sparkles, X } from "lucide-react";
import { Button, Textarea, Input, Select } from "@/components/ui";
import { Card } from "@/components/kit";
import type { TalentSearchBody } from "@/lib/api";

/** Criteria the panel emits — the screen appends `limit`/`offset` for paging. */
export type TalentSearchCriteria = Pick<
  TalentSearchBody,
  "jd_text" | "query_text" | "skills" | "min_experience"
>;

const MIN_EXP_YEARS = [1, 2, 3, 5, 7, 10] as const;

/* -------------------------------------------------------------------------- */
/* Skill chip field — a free-text tag input (skills are not a fixed enum, so a  */
/* tag field is the right control, not a UUID/key text box). Focus treatment    */
/* mirrors the system field tokens (single boundary + focus ring).              */
/* -------------------------------------------------------------------------- */

function SkillChipField({
  skills,
  onChange,
  placeholder,
  ariaLabel,
}: {
  skills: string[];
  onChange: (next: string[]) => void;
  placeholder: string;
  ariaLabel: string;
}) {
  const [draft, setDraft] = React.useState("");

  function commit(raw: string) {
    const value = raw.trim();
    if (!value) return;
    // De-dupe case-insensitively; cap at the backend limit (25).
    const exists = skills.some((s) => s.toLowerCase() === value.toLowerCase());
    if (!exists && skills.length < 25) onChange([...skills, value]);
    setDraft("");
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      commit(draft);
    } else if (e.key === "Backspace" && draft === "" && skills.length > 0) {
      onChange(skills.slice(0, -1));
    }
  }

  return (
    <div
      className={
        "flex min-h-[2.75rem] w-full flex-wrap items-center gap-1.5 rounded-xl border border-[var(--border-default)] bg-transparent px-2.5 py-1.5 " +
        "transition-[border-color,box-shadow,background-color] duration-150 hover:border-[var(--border-strong)] " +
        "focus-within:border-[var(--field-focus-border)] focus-within:bg-[var(--surface-card)] focus-within:shadow-[0_0_0_4px_var(--field-focus-ring)]"
      }
    >
      {skills.map((skill) => (
        <span
          key={skill}
          className="inline-flex items-center gap-1 rounded-full bg-[var(--viz-indigo-soft)] py-0.5 pl-2.5 pr-1 text-xs font-medium text-[var(--viz-indigo)]"
        >
          {skill}
          <button
            type="button"
            onClick={() => onChange(skills.filter((s) => s !== skill))}
            aria-label={`${ariaLabel}: ${skill} ✕`}
            className="flex size-4 items-center justify-center rounded-full text-[var(--viz-indigo)]/80 outline-none transition-colors hover:bg-[var(--viz-indigo)]/15 focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
          >
            <X aria-hidden className="size-3" strokeWidth={2.4} />
          </button>
        </span>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={() => commit(draft)}
        placeholder={skills.length === 0 ? placeholder : ""}
        aria-label={ariaLabel}
        className="h-7 min-w-[8ch] flex-1 bg-transparent px-1 text-sm font-medium text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none"
      />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Search panel                                                                 */
/* -------------------------------------------------------------------------- */

/**
 * The hiring-need composer. A recruiter pastes a JD (posted OR not-yet-posted),
 * adds required skills + a minimum-experience floor, and/or types a free-text
 * need, then runs an AI semantic search over the consented CV pool. The primary
 * CTA is disabled until at least one criterion exists (mirrors the backend 422).
 */
export function TalentSearchPanel({
  onSearch,
  onClear,
  loading,
  hasResults,
}: {
  onSearch: (criteria: TalentSearchCriteria) => void;
  onClear: () => void;
  loading: boolean;
  hasResults: boolean;
}) {
  const t = useTranslations("talentPool");

  const [jdText, setJdText] = React.useState("");
  const [queryText, setQueryText] = React.useState("");
  const [skills, setSkills] = React.useState<string[]>([]);
  const [minExp, setMinExp] = React.useState("");

  const hasCriteria =
    jdText.trim().length > 0 || queryText.trim().length > 0 || skills.length > 0;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!hasCriteria) return;
    onSearch({
      jd_text: jdText.trim() || undefined,
      query_text: queryText.trim() || undefined,
      skills: skills.length ? skills : undefined,
      min_experience: minExp ? Number(minExp) : undefined,
    });
  }

  function reset() {
    setJdText("");
    setQueryText("");
    setSkills([]);
    setMinExp("");
    onClear();
  }

  const minExpOptions = [
    { value: "", label: t("minExpAny") },
    ...MIN_EXP_YEARS.map((n) => ({ value: String(n), label: t("minExpYears", { years: n }) })),
  ];

  return (
    <Card className="p-5">
      <form onSubmit={submit} className="space-y-4">
        {/* JD paste — the primary input (external / not-yet-posted JD welcome). */}
        <div>
          <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
            <label
              htmlFor="talent-jd"
              className="text-sm font-semibold text-[var(--text-primary)]"
            >
              {t("jdLabel")}
            </label>
            <span className="inline-flex items-center gap-1 rounded-full bg-[var(--content-ai-soft)] px-2 py-0.5 text-[0.6875rem] font-medium text-[var(--content-ai)]">
              <Sparkles aria-hidden className="size-3" strokeWidth={1.9} />
              {t("jdBadge")}
            </span>
          </div>
          <Textarea
            id="talent-jd"
            rows={5}
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            maxLength={8000}
            placeholder={t("jdPlaceholder")}
            help={t("jdHelp")}
          />
        </div>

        {/* Skills + minimum experience */}
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="sm:col-span-2">
            <label className="mb-1.5 block text-sm font-semibold text-[var(--text-primary)]">
              {t("skillsLabel")}
            </label>
            <SkillChipField
              skills={skills}
              onChange={setSkills}
              placeholder={t("skillsPlaceholder")}
              ariaLabel={t("skillsLabel")}
            />
            <p className="mt-1 text-xs text-[var(--text-secondary)]">{t("skillsHelp")}</p>
          </div>
          <Select
            label={t("minExpLabel")}
            options={minExpOptions}
            value={minExp}
            onChange={(e) => setMinExp(e.target.value)}
          />
        </div>

        {/* Free-text quick need */}
        <Input
          label={t("queryLabel")}
          value={queryText}
          onChange={(e) => setQueryText(e.target.value)}
          maxLength={1000}
          placeholder={t("queryPlaceholder")}
        />

        {/* Footer: AI provenance note + actions */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
          <p className="flex items-center gap-1.5 type-small text-muted-foreground">
            <Sparkles aria-hidden className="size-4 shrink-0 text-[var(--content-ai)]" strokeWidth={1.8} />
            {t("aiHint")}
          </p>
          <div className="flex items-center gap-2">
            {hasResults && (
              <Button type="button" variant="ghost" size="sm" onClick={reset} disabled={loading}>
                {t("clear")}
              </Button>
            )}
            <Button type="submit" variant="primary" size="sm" loading={loading} disabled={!hasCriteria}>
              {!loading && <Search className="size-4" strokeWidth={1.9} />}
              {t("searchCta")}
            </Button>
          </div>
        </div>
        {!hasCriteria && (
          <p className="type-small text-muted-foreground" role="status">
            {t("needCriteriaHint")}
          </p>
        )}
      </form>
    </Card>
  );
}
