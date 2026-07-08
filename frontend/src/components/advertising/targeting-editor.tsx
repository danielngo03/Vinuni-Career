"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Target, Lock, Plus, X } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { SegmentedControl } from "@/components/ui";
import {
  CLOSED_VOCAB,
  MODE_AUTOMATIC,
  MODE_MANUAL,
  TARGETING_DIMENSIONS,
  activeDimensions,
  isTagDimension,
  type TargetingDimension,
  type TargetingMode,
} from "@/lib/advertising/targeting";

export interface TargetingEditorValue {
  mode: TargetingMode;
  dimensions: Partial<Record<TargetingDimension, string[]>>;
}

/**
 * Audience-targeting section for the placement form (spec §4/§7). A partner
 * chooses `automatic` (broad reach) or `manual` (pick allowlisted values across
 * the six privacy-safe dimensions). When the placement is `university_restricted`
 * the whole section is READ-ONLY with a clear "set by university" note — the
 * partner cannot edit it (the API 422s `restricted_by_university`).
 *
 * Only the six allowlisted dimensions are ever offered; no PII / sensitive
 * dimension is available. Values are normalised on submit by
 * `buildTargetingDescriptor`.
 */
export function TargetingEditor({
  value,
  onChange,
  restricted,
}: {
  value: TargetingEditorValue;
  onChange: (next: TargetingEditorValue) => void;
  /** The stored descriptor is university-restricted — render read-only. */
  restricted: boolean;
}) {
  const t = useTranslations("advertising");

  if (restricted) {
    return <RestrictedView descriptor={value} />;
  }

  const isManual = value.mode === MODE_MANUAL;

  function setMode(mode: string) {
    onChange({
      mode: mode === MODE_MANUAL ? MODE_MANUAL : MODE_AUTOMATIC,
      // Keep any picked values so toggling manual->automatic->manual is lossless.
      dimensions: value.dimensions,
    });
  }

  function setDimension(dim: TargetingDimension, values: string[]) {
    const next: TargetingEditorValue["dimensions"] = { ...value.dimensions };
    if (values.length > 0) next[dim] = values;
    else delete next[dim];
    onChange({ mode: value.mode, dimensions: next });
  }

  return (
    <section
      className="space-y-3 rounded-xl border border-[var(--border-default)] bg-[var(--bg-subtle)] px-3.5 py-3.5"
      aria-labelledby="targeting-heading"
    >
      <div className="flex items-start gap-2.5">
        <span className="flex size-6 shrink-0 items-center justify-center rounded-md icon-chip-neutral shadow-sm">
          <Target aria-hidden weight="duotone" className="size-3.5 text-white" />
        </span>
        <div className="min-w-0">
          <h3
            id="targeting-heading"
            className="text-sm font-bold text-[var(--text-primary)]"
          >
            {t("targeting.title")}
          </h3>
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
            {t("targeting.subtitle")}
          </p>
        </div>
      </div>

      <div>
        <span className="mb-1.5 block text-xs font-semibold text-[var(--text-primary)]">
          {t("targeting.modeLabel")}
        </span>
        <SegmentedControl
          ariaLabel={t("targeting.modeLabel")}
          size="sm"
          value={isManual ? MODE_MANUAL : MODE_AUTOMATIC}
          onValueChange={setMode}
          options={[
            { value: MODE_AUTOMATIC, label: t("targeting.mode.automatic") },
            { value: MODE_MANUAL, label: t("targeting.mode.manual") },
          ]}
        />
        <p className="mt-1.5 text-xs text-[var(--text-muted)]">
          {isManual ? t("targeting.manualHint") : t("targeting.automaticHint")}
        </p>
      </div>

      {isManual && (
        <div className="space-y-3.5 border-t border-[var(--border-default)] pt-3.5">
          {TARGETING_DIMENSIONS.map((dim) => (
            <DimensionField
              key={dim}
              dim={dim}
              values={value.dimensions[dim] ?? []}
              onChange={(vals) => setDimension(dim, vals)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/* Read-only restricted view                                                  */
/* -------------------------------------------------------------------------- */

function RestrictedView({ descriptor }: { descriptor: TargetingEditorValue }) {
  const t = useTranslations("advertising");
  const active = activeDimensions(descriptor);

  return (
    <section
      className="space-y-3 rounded-xl border border-[var(--amber-600)]/40 bg-[var(--amber-50)] px-3.5 py-3.5"
      aria-labelledby="targeting-heading"
    >
      <div className="flex items-start gap-2.5">
        <span className="flex size-6 shrink-0 items-center justify-center rounded-md icon-chip-warning shadow-sm">
          <Lock aria-hidden weight="duotone" className="size-3.5 text-white" />
        </span>
        <div className="min-w-0">
          <h3
            id="targeting-heading"
            className="flex flex-wrap items-center gap-2 text-sm font-bold text-[var(--text-primary)]"
          >
            {t("targeting.title")}
            <span className="rounded-full bg-[var(--amber-100)] px-2 py-0.5 text-[11px] font-semibold text-[var(--amber-700)]">
              {t("targeting.restrictedBadge")}
            </span>
          </h3>
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
            {t("targeting.restrictedNote")}
          </p>
        </div>
      </div>

      {active.length === 0 ? (
        <p className="text-xs text-[var(--text-muted)]">
          {t("targeting.emptyRestricted")}
        </p>
      ) : (
        <dl className="space-y-2">
          {active.map((dim) => (
            <div key={dim} className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
              <dt className="text-xs font-semibold text-[var(--text-primary)]">
                {t(`targeting.dimensions.${dim}`)}:
              </dt>
              <dd className="flex flex-wrap gap-1.5">
                {(descriptor.dimensions[dim] ?? []).map((v) => (
                  <span
                    key={v}
                    className="rounded-full border border-[var(--amber-600)]/30 bg-white/70 px-2 py-0.5 text-[11px] font-medium text-[var(--text-primary)]"
                  >
                    {dimensionValueLabel(dim, v, t)}
                  </span>
                ))}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/* Per-dimension field                                                        */
/* -------------------------------------------------------------------------- */

function DimensionField({
  dim,
  values,
  onChange,
}: {
  dim: TargetingDimension;
  values: string[];
  onChange: (values: string[]) => void;
}) {
  const t = useTranslations("advertising");
  const label = t(`targeting.dimensions.${dim}`);

  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-[var(--text-primary)]">
          {label}
        </span>
        {values.length > 0 && (
          <span className="text-[11px] font-medium text-[var(--text-muted)]">
            {t("targeting.selectedCount", { count: values.length })}
          </span>
        )}
      </div>
      {isTagDimension(dim) ? (
        <TagField
          dim={dim}
          values={values}
          onChange={onChange}
          placeholder={t("targeting.addTagPlaceholder")}
          addLabel={t("targeting.addTag")}
          removeLabelFor={(v) => t("targeting.removeTag", { value: v })}
          hint={t(`targeting.dimensionHint.${dim}`)}
        />
      ) : (
        <ChipToggleGroup
          dim={dim}
          options={CLOSED_VOCAB[dim] ?? []}
          selected={values}
          onChange={onChange}
          ariaLabel={label}
        />
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Closed-vocab chip toggles                                                  */
/* -------------------------------------------------------------------------- */

function ChipToggleGroup({
  dim,
  options,
  selected,
  onChange,
  ariaLabel,
}: {
  dim: TargetingDimension;
  options: readonly string[];
  selected: string[];
  onChange: (values: string[]) => void;
  ariaLabel: string;
}) {
  const t = useTranslations("advertising");

  function toggle(value: string) {
    onChange(
      selected.includes(value)
        ? selected.filter((v) => v !== value)
        : [...selected, value],
    );
  }

  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label={ariaLabel}>
      {options.map((value) => {
        const on = selected.includes(value);
        return (
          <button
            key={value}
            type="button"
            aria-pressed={on}
            onClick={() => toggle(value)}
            className={cn(
              "inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-primary)]",
              on
                ? "border-[var(--brand-primary)] bg-[var(--brand-primary)] text-white"
                : "border-[var(--border-default)] bg-white text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
            )}
          >
            {dimensionValueLabel(dim, value, t)}
          </button>
        );
      })}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Open coarse-tag chip input                                                 */
/* -------------------------------------------------------------------------- */

function TagField({
  dim,
  values,
  onChange,
  placeholder,
  addLabel,
  removeLabelFor,
  hint,
}: {
  dim: TargetingDimension;
  values: string[];
  onChange: (values: string[]) => void;
  placeholder: string;
  addLabel: string;
  removeLabelFor: (value: string) => string;
  hint: string;
}) {
  const [text, setText] = useState("");
  const inputId = `targeting-tag-${dim}`;

  function add() {
    const token = text.trim().toLowerCase().slice(0, 64);
    if (!token) return;
    if (!values.includes(token)) onChange([...values, token]);
    setText("");
  }

  function remove(value: string) {
    onChange(values.filter((v) => v !== value));
  }

  return (
    <div className="space-y-1.5">
      {values.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {values.map((value) => (
            <li key={value}>
              <span className="inline-flex items-center gap-1 rounded-full border border-[var(--border-default)] bg-white py-1 pl-3 pr-1.5 text-xs font-medium text-[var(--text-primary)]">
                {value}
                <button
                  type="button"
                  onClick={() => remove(value)}
                  aria-label={removeLabelFor(value)}
                  className="flex size-4 items-center justify-center rounded-full text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--brand-primary)]"
                >
                  <X aria-hidden weight="bold" className="size-3" />
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
      <div className="flex items-center gap-2">
        <input
          id={inputId}
          type="text"
          value={text}
          maxLength={64}
          placeholder={placeholder}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          className="min-w-0 flex-1 rounded-lg border border-[var(--border-default)] bg-white px-3 py-1.5 text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
        />
        <button
          type="button"
          onClick={add}
          disabled={text.trim().length === 0}
          className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-[var(--border-default)] bg-white px-2.5 py-1.5 text-xs font-semibold text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-subtle)] disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--brand-primary)]"
        >
          <Plus aria-hidden weight="bold" className="size-3.5" />
          {addLabel}
        </button>
      </div>
      <p className="text-[11px] text-[var(--text-muted)]">{hint}</p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Value labels                                                               */
/* -------------------------------------------------------------------------- */

/** Localized label for a closed-vocab value; a raw tag renders as-is. */
function dimensionValueLabel(
  dim: TargetingDimension,
  value: string,
  t: ReturnType<typeof useTranslations>,
): string {
  const key = `targeting.values.${dim}.${value}`;
  return t.has(key) ? t(key) : value;
}
