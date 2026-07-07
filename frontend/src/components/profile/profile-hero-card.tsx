"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import {
  Briefcase,
  Camera,
  CheckCircle,
  EnvelopeSimple,
  Trash,
  WarningCircle,
} from "@phosphor-icons/react";
import { Switch } from "@/components/ui";
import {
  profileApi,
  type StudentProfile,
  type UpdateProfileBody,
} from "@/lib/api";
import { useProfileMutations } from "./use-profile-mutations";

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
    <span className="text-2xl font-bold uppercase text-[var(--text-inverted)] select-none">
      {letters}
    </span>
  );
}

/**
 * Identity header for the slim profile: avatar (change/remove), read-only name
 * and email (account-owned), and the single "Open to work" toggle recruiters
 * can see. Career content lives entirely in the student's CVs.
 */
export function ProfileHeroCard({ profile }: { profile: StudentProfile }) {
  const t = useTranslations("profile.avatar");
  const th = useTranslations("profile.header");
  const fileRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const { setProfile, handleError, notifySaved } = useProfileMutations();

  const currentUrl = preview ?? profile.avatar_url ?? null;
  const displayName = profile.display_name || "?";

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

  const openToWork = useMutation({
    mutationFn: (next: boolean) => {
      const body: UpdateProfileBody = {
        is_open_to_work: next,
        expected_version: profile.version,
      };
      return profileApi.updateMine(body);
    },
    onSuccess: (updated) => {
      setProfile(updated);
      notifySaved();
    },
    onError: handleError,
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

  const avatarBusy = upload.isPending || removeMut.isPending;

  return (
    <section
      className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-6 shadow-[var(--shadow-sm)]"
      aria-label={th("ariaLabel")}
    >
      <div className="flex flex-wrap items-start gap-5">
        {/* Avatar with camera overlay */}
        <button
          type="button"
          aria-label={t("changeCta")}
          disabled={avatarBusy}
          onClick={() => fileRef.current?.click()}
          className="group relative shrink-0 rounded-full outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40 focus-visible:ring-offset-2"
        >
          <div className="flex h-20 w-20 items-center justify-center overflow-hidden rounded-full border border-[var(--border-strong)] bg-[var(--brand-primary)] shadow-sm">
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
          <span className="absolute inset-0 flex items-center justify-center rounded-full bg-black/40 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
            <Camera aria-hidden className="h-6 w-6 text-white" weight="bold" />
          </span>
          {avatarBusy && (
            <span className="absolute inset-0 flex items-center justify-center rounded-full bg-black/50">
              <span className="h-5 w-5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            </span>
          )}
        </button>

        {/* Identity */}
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-xl font-bold text-[var(--text-primary)]">
            {displayName}
          </h2>
          <p className="mt-1 flex items-center gap-1.5 text-sm text-[var(--text-secondary)]">
            <EnvelopeSimple
              aria-hidden
              weight="duotone"
              className="size-4 shrink-0 text-[var(--text-muted)]"
            />
            <span className="truncate">{profile.email}</span>
          </p>

          {/* Avatar CTAs */}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={avatarBusy}
              onClick={() => fileRef.current?.click()}
              className="text-xs font-semibold text-[var(--brand-primary)] outline-none hover:underline focus-visible:underline disabled:cursor-not-allowed disabled:opacity-50"
            >
              {t("changeCta")}
            </button>
            {(currentUrl || profile.avatar_url) && (
              <>
                <span className="text-xs text-[var(--text-muted)]">·</span>
                <button
                  type="button"
                  disabled={avatarBusy}
                  onClick={() => removeMut.mutate()}
                  className="flex items-center gap-1 text-xs font-semibold text-[var(--brand-red)] outline-none hover:underline focus-visible:underline disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Trash aria-hidden weight="duotone" className="size-3" />
                  {t("removeCta")}
                </button>
              </>
            )}
          </div>
          {localError && (
            <p className="mt-1 flex items-center gap-1 text-xs text-[var(--brand-red)]">
              <WarningCircle
                aria-hidden
                weight="duotone"
                className="size-3.5 shrink-0"
              />
              {localError}
            </p>
          )}
          {saved && !localError && (
            <p className="mt-1 flex items-center gap-1 text-xs text-[var(--color-success)]">
              <CheckCircle aria-hidden weight="fill" className="size-3.5 shrink-0" />
              {t("saved")}
            </p>
          )}
        </div>
      </div>

      {/* Open to work toggle */}
      <div className="mt-5 flex flex-wrap items-start justify-between gap-4 border-t border-[var(--border-default)] pt-5">
        <div className="flex min-w-0 items-start gap-3">
          <span
            className={`flex size-9 shrink-0 items-center justify-center rounded-xl shadow-sm ${
              profile.is_open_to_work ? "icon-chip-success" : "icon-chip-neutral"
            }`}
          >
            <Briefcase aria-hidden weight="duotone" className="size-4 text-white" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {th("openToWorkLabel")}
            </p>
            <p className="mt-0.5 text-xs leading-relaxed text-[var(--text-secondary)]">
              {th("openToWorkExplain")}
            </p>
          </div>
        </div>
        <Switch
          label={th("openToWorkLabel")}
          hideLabel
          disabled={openToWork.isPending}
          checked={profile.is_open_to_work}
          onCheckedChange={(next) => openToWork.mutate(next)}
        />
      </div>

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
