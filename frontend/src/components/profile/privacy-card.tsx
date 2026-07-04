"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { EyeSlash, Info } from "@phosphor-icons/react";
import { Button, Select, Switch } from "@/components/ui";
import { SectionCard } from "@/components/settings/section-card";
import { useProfileLabels } from "@/lib/profile/labels";
import {
  CONTACT_VISIBILITIES,
  OPEN_TO_WORK_TYPES,
  PROFILE_VISIBILITIES,
  profileApi,
  type ContactVisibility,
  type ProfileVisibility,
  type StudentProfile,
  type UpdateProfileBody,
} from "@/lib/api";
import { useProfileMutations } from "./use-profile-mutations";

interface PrivacyState {
  profile_visibility: ProfileVisibility;
  show_email: ContactVisibility;
  show_phone: ContactVisibility;
  is_open_to_work: boolean;
  open_to_work_types: string[];
}

function toState(p: StudentProfile): PrivacyState {
  return {
    profile_visibility: (p.profile_visibility as ProfileVisibility) ?? "vinuni_only",
    show_email: (p.show_email as ContactVisibility) ?? "hidden",
    show_phone: (p.show_phone as ContactVisibility) ?? "hidden",
    is_open_to_work: p.is_open_to_work,
    open_to_work_types: [...p.open_to_work_types],
  };
}

function sameSet(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((x) => b.includes(x));
}

export function PrivacyCard({ profile }: { profile: StudentProfile }) {
  const t = useTranslations("profile.privacy");
  const tc = useTranslations("common");
  const labels = useProfileLabels();
  const { setProfile, handleError, notifySaved } = useProfileMutations();

  const [state, setState] = useState<PrivacyState>(() => toState(profile));

  useEffect(() => {
    setState(toState(profile));
  }, [profile]);

  const initial = toState(profile);
  const dirty =
    state.profile_visibility !== initial.profile_visibility ||
    state.show_email !== initial.show_email ||
    state.show_phone !== initial.show_phone ||
    state.is_open_to_work !== initial.is_open_to_work ||
    !sameSet(state.open_to_work_types, initial.open_to_work_types);

  const save = useMutation({
    mutationFn: () => {
      const body: UpdateProfileBody = {
        profile_visibility: state.profile_visibility,
        show_email: state.show_email,
        show_phone: state.show_phone,
        is_open_to_work: state.is_open_to_work,
        open_to_work_types: state.open_to_work_types,
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

  const toggleWorkType = (type: string) => {
    setState((s) => ({
      ...s,
      open_to_work_types: s.open_to_work_types.includes(type)
        ? s.open_to_work_types.filter((x) => x !== type)
        : [...s.open_to_work_types, type],
    }));
  };

  return (
    <SectionCard
      title={t("title")}
      description={t("intro")}
      icon={EyeSlash}
      iconGradient="icon-chip-neutral"
    >
      <div className="space-y-6">
        {/* Overall visibility */}
        <div>
          <Select
            label={t("visibilityLabel")}
            value={state.profile_visibility}
            onChange={(e) =>
              setState((s) => ({
                ...s,
                profile_visibility: e.target.value as ProfileVisibility,
              }))
            }
            options={PROFILE_VISIBILITIES.map((v) => ({
              value: v,
              label: labels.visibility(v),
            }))}
          />
          <p
            className="mt-2 flex items-start gap-2 rounded-xl border border-[var(--glass-border)] bg-[var(--glass-surface-light)] px-3.5 py-2.5 text-xs text-[var(--text-secondary)] backdrop-blur-sm"
            aria-live="polite"
          >
            <Info
              aria-hidden
              weight="duotone"
              className="mt-0.5 size-4 shrink-0 text-[var(--brand-primary)]"
            />
            <span>{t(`visibilityExplain.${state.profile_visibility}`)}</span>
          </p>
        </div>

        {/* Contact field gates */}
        <fieldset className="space-y-4">
          <legend className="text-sm font-semibold text-[var(--text-primary)]">
            {t("contactLegend")}
          </legend>
          <p className="text-xs text-[var(--text-secondary)]">
            {t("contactIntro")}
          </p>
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <Select
              label={t("showEmail")}
              help={t(`contactExplain.${state.show_email}`)}
              value={state.show_email}
              onChange={(e) =>
                setState((s) => ({
                  ...s,
                  show_email: e.target.value as ContactVisibility,
                }))
              }
              options={CONTACT_VISIBILITIES.map((v) => ({
                value: v,
                label: labels.contact(v),
              }))}
            />
            <Select
              label={t("showPhone")}
              help={t(`contactExplain.${state.show_phone}`)}
              value={state.show_phone}
              onChange={(e) =>
                setState((s) => ({
                  ...s,
                  show_phone: e.target.value as ContactVisibility,
                }))
              }
              options={CONTACT_VISIBILITIES.map((v) => ({
                value: v,
                label: labels.contact(v),
              }))}
            />
          </div>
        </fieldset>

        {/* Open to work */}
        <fieldset className="space-y-3">
          <legend className="sr-only">{t("openToWorkLabel")}</legend>
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {t("openToWorkLabel")}
              </p>
              <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                {t("openToWorkHelp")}
              </p>
            </div>
            <Switch
              label={t("openToWorkLabel")}
              hideLabel
              checked={state.is_open_to_work}
              onCheckedChange={(v) =>
                setState((s) => ({ ...s, is_open_to_work: v }))
              }
            />
          </div>
          {state.is_open_to_work && (
            <div className="flex flex-wrap gap-2 pt-1">
              {OPEN_TO_WORK_TYPES.map((type) => {
                const active = state.open_to_work_types.includes(type);
                return (
                  <button
                    key={type}
                    type="button"
                    role="checkbox"
                    aria-checked={active}
                    onClick={() => toggleWorkType(type)}
                    className={
                      active
                        ? "rounded-full border-2 border-[var(--brand-primary)] bg-[var(--blue-50)] px-3.5 py-1.5 text-xs font-semibold text-[var(--brand-primary)] outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
                        : "rounded-full border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] backdrop-blur-md px-3.5 py-1.5 text-xs font-medium text-[var(--text-secondary)] outline-none transition-colors hover:border-[var(--brand-primary)]/40 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
                    }
                  >
                    {labels.openToWork(type)}
                  </button>
                );
              })}
            </div>
          )}
        </fieldset>

        <div className="flex justify-end">
          <Button
            variant="primary"
            loading={save.isPending}
            disabled={!dirty || save.isPending}
            onClick={() => save.mutate()}
          >
            {save.isPending ? tc("saving") : tc("save")}
          </Button>
        </div>
      </div>
    </SectionCard>
  );
}
