"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import {
  Briefcase,
  Camera,
  CheckCircle,
  LightbulbFilament,
  MapPin,
  Sparkle,
  Trash,
  WarningCircle,
} from "@phosphor-icons/react";
import { profileApi, type StudentProfile } from "@/lib/api";
import { useProfileMutations } from "./use-profile-mutations";
import { cn } from "@/lib/utils";

const ACCEPT = "image/png,image/jpeg,image/webp";
const MAX_MB = 3;
const MAX_BYTES = MAX_MB * 1024 * 1024;

function Initials({ name }: { name: string }) {
  const parts = name.trim().split(/\s+/);
  const first = parts[0] ?? "";
  const last = parts.length >= 2 ? (parts[parts.length - 1] ?? "") : "";
  const letters =
    parts.length >= 2 ? (first[0] ?? "") + (last[0] ?? "") : (first[0] ?? "?");
  return (
    <span className="text-2xl font-bold text-white/90 uppercase select-none">
      {letters}
    </span>
  );
}

function buildNudges(p: StudentProfile): string[] {
  const out: string[] = [];
  if (!p.headline) out.push("headline");
  if (!p.summary) out.push("summary");
  if (p.education.length === 0) out.push("education");
  if (p.experience.length === 0) out.push("experience");
  if (p.skills.length === 0) out.push("skills");
  if (!p.major || !p.degree_level || !p.graduation_year) out.push("academic");
  if (p.links.length === 0) out.push("links");
  return out;
}

type ProfileInsightKey =
  | "insightAddSkills"
  | "insightAddExperience"
  | "insightAddHeadline"
  | "insightAddLinks"
  | "insightLowCompletion"
  | "insightNearComplete";

function deriveProfileInsights(p: StudentProfile): ProfileInsightKey[] {
  const out: ProfileInsightKey[] = [];
  const pct = Math.max(0, Math.min(100, p.profile_completion));
  if (p.skills.length === 0) out.push("insightAddSkills");
  if (p.experience.length === 0) out.push("insightAddExperience");
  if (!p.headline) out.push("insightAddHeadline");
  if (p.links.length === 0) out.push("insightAddLinks");
  if (out.length === 0 && pct < 80) out.push("insightLowCompletion");
  if (out.length === 0 && pct >= 80) out.push("insightNearComplete");
  return out.slice(0, 3);
}

/**
 * Unified profile hero card: avatar upload + identity + location +
 * profile completion bar + next-step nudges — all in one glass card.
 * Replaces the previous separate AvatarUploadSection + CompletionMeter pair.
 */
export function ProfileHeroCard({ profile }: { profile: StudentProfile }) {
  const t = useTranslations("profile.avatar");
  const tc = useTranslations("profile.completion");
  const tn = useTranslations("profile.nudges");
  const tp = useTranslations("profile.privacy");
  const tai = useTranslations("profile.aiInsights");
  const fileRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const { setProfile } = useProfileMutations();

  const currentUrl = preview ?? profile.avatar_url ?? null;
  const displayName = profile.display_name || "?";

  const pct = Math.max(0, Math.min(100, profile.profile_completion));
  const complete = pct >= 100;
  const nudges = complete ? [] : buildNudges(profile).slice(0, 2);
  const aiInsights = complete ? [] : deriveProfileInsights(profile);

  const upload = useMutation({
    mutationFn: (file: File) => profileApi.uploadAvatar(file),
    onSuccess: (res) => {
      setProfile({ ...profile, avatar_url: res.avatar_url });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
      setLocalError(null);
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : t("uploadError");
      setLocalError(msg);
      setPreview(null);
    },
  });

  const removeMut = useMutation({
    mutationFn: () => profileApi.removeAvatar(),
    onSuccess: () => {
      setProfile({ ...profile, avatar_url: null });
      setPreview(null);
      setLocalError(null);
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : t("removeError");
      setLocalError(msg);
    },
  });

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setLocalError(null);
    if (file.size > MAX_BYTES) {
      setLocalError(t("tooLarge", { maxMb: MAX_MB }));
      e.target.value = "";
      return;
    }
    const objectUrl = URL.createObjectURL(file);
    setPreview(objectUrl);
    upload.mutate(file);
    e.target.value = "";
  }

  const isPending = upload.isPending || removeMut.isPending;
  const location = [profile.location_city, profile.location_country]
    .filter(Boolean)
    .join(", ");

  return (
    <section
      className="rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] p-6 backdrop-blur-md shadow-[0_2px_12px_rgba(11,34,57,0.06)]"
      aria-label={tc("title")}
    >
      <div className="flex flex-wrap items-start gap-5">
        {/* Avatar with camera overlay */}
        <button
          type="button"
          aria-label={t("changeCta")}
          disabled={isPending}
          onClick={() => fileRef.current?.click()}
          className="relative shrink-0 group rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40 focus-visible:ring-offset-2"
        >
          <div className="h-20 w-20 rounded-full overflow-hidden border-2 border-[var(--glass-border-strong)] bg-gradient-to-br from-[var(--gray-700)] to-[var(--gray-900)] flex items-center justify-center shadow-md">
            {currentUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={currentUrl}
                alt={displayName}
                className="h-full w-full object-cover"
              />
            ) : (
              <Initials name={displayName} />
            )}
          </div>
          <span className="absolute inset-0 rounded-full bg-black/40 opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100 transition-opacity flex items-center justify-center">
            <Camera aria-hidden className="h-6 w-6 text-white" weight="bold" />
          </span>
          {isPending && (
            <span className="absolute inset-0 rounded-full bg-black/50 flex items-center justify-center">
              <span className="h-5 w-5 rounded-full border-2 border-white/30 border-t-white animate-spin" />
            </span>
          )}
        </button>

        {/* Identity + completion */}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-2">
            {/* Name + headline + location */}
            <div className="min-w-0">
              <h2 className="text-xl font-bold text-[var(--text-primary)] truncate">
                {displayName}
              </h2>
              {profile.headline && (
                <p className="mt-0.5 text-sm text-[var(--text-secondary)] line-clamp-1">
                  {profile.headline}
                </p>
              )}
              {location && (
                <p className="mt-1 flex items-center gap-1 text-xs text-[var(--text-muted)]">
                  <MapPin aria-hidden weight="duotone" className="size-3.5 shrink-0" />
                  {location}
                </p>
              )}
              {/* Avatar upload CTAs */}
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={isPending}
                  onClick={() => fileRef.current?.click()}
                  className="text-xs font-medium text-[var(--brand-primary)] hover:underline disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {t("changeCta")}
                </button>
                {(currentUrl || profile.avatar_url) && (
                  <>
                    <span className="text-xs text-[var(--text-muted)]">·</span>
                    <button
                      type="button"
                      disabled={isPending}
                      onClick={() => removeMut.mutate()}
                      className="flex items-center gap-1 text-xs font-medium text-[var(--brand-red)] hover:underline disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Trash aria-hidden weight="duotone" className="size-3" />
                      {t("removeCta")}
                    </button>
                  </>
                )}
              </div>
              {localError && (
                <p className="mt-1 flex items-center gap-1 text-xs text-[var(--brand-red)]">
                  <WarningCircle aria-hidden weight="duotone" className="size-3.5 shrink-0" />
                  {localError}
                </p>
              )}
              {saved && !localError && (
                <p className="mt-1 flex items-center gap-1 text-xs text-[var(--teal-600)]">
                  <CheckCircle aria-hidden weight="fill" className="size-3.5 shrink-0" />
                  {t("saved")}
                </p>
              )}
            </div>

            {/* Completion badge */}
            <div className="shrink-0 text-right">
              <span
                className={cn(
                  "text-2xl font-bold tabular-nums",
                  complete ? "text-[var(--teal-600)]" : "text-[var(--brand-primary)]",
                )}
                aria-label={tc("ariaLabel", { pct })}
              >
                {pct}%
              </span>
              <p className="text-[11px] text-[var(--text-muted)]">{tc("title")}</p>
            </div>
          </div>

          {/* Progress bar */}
          <div
            className="mt-3 h-2 w-full overflow-hidden rounded-full bg-[var(--bg-muted)]"
            role="progressbar"
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={tc("ariaLabel", { pct })}
          >
            <div
              className={cn(
                "h-full rounded-full transition-[width] duration-500 motion-reduce:transition-none",
                complete ? "bg-[var(--teal-600)]" : "bg-[var(--brand-primary)]",
              )}
              style={{ width: `${pct}%` }}
            />
          </div>

          {/* Next-step nudges */}
          {!complete && nudges.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
              {nudges.map((key) => (
                <span
                  key={key}
                  className="flex items-center gap-1 text-xs text-[var(--text-secondary)]"
                >
                  <LightbulbFilament
                    aria-hidden
                    weight="duotone"
                    className="size-3.5 shrink-0 text-[var(--ai-accent)]"
                  />
                  {tn(key)}
                </span>
              ))}
            </div>
          )}
          {complete && (
            <p className="mt-2 flex items-center gap-1 text-xs font-medium text-[var(--teal-600)]">
              <CheckCircle aria-hidden weight="fill" className="size-4" />
              {tc("done")}
            </p>
          )}

          {/* Open-to-work signal */}
          {profile.is_open_to_work && (
            <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-[var(--glass-border)] pt-3">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--teal-50)] px-3 py-1 text-xs font-semibold text-[var(--teal-700)] ring-1 ring-inset ring-[var(--teal-100)]">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--teal-500)] animate-pulse" />
                {tp("openToWorkLabel")}
              </span>
              {profile.open_to_work_type_labels.map((label) => (
                <span
                  key={label}
                  className="inline-flex items-center gap-1 rounded-full border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] px-2.5 py-0.5 text-[11px] font-medium text-[var(--text-secondary)] backdrop-blur-sm"
                >
                  <Briefcase aria-hidden weight="duotone" className="size-3 text-[var(--brand-primary)]" />
                  {label}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* AI Profile Insights */}
      {aiInsights.length > 0 && (
        <section
          className="mt-4 rounded-2xl border border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-[var(--glass-surface-light)] p-4 backdrop-blur-xl"
          aria-label={tai("title")}
        >
          <h3 className="mb-2.5 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
            <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-info shadow-sm">
              <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
            </span>
            {tai("title")}
          </h3>
          <ul className="space-y-1.5">
            {aiInsights.map((key) => (
              <li key={key} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                <LightbulbFilament aria-hidden weight="duotone" className="mt-0.5 size-3.5 shrink-0 text-[var(--ai-accent)]" />
                {tai(key)}
              </li>
            ))}
          </ul>
        </section>
      )}

      <input
        ref={fileRef}
        type="file"
        accept={ACCEPT}
        className="sr-only"
        aria-hidden="true"
        tabIndex={-1}
        onChange={handleFileChange}
      />
    </section>
  );
}
