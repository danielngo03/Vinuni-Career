"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { EyeSlash, Info } from "@phosphor-icons/react";
import { Button, Select } from "@/components/ui";
import { SectionCard } from "@/components/settings/section-card";
import { useProfileLabels } from "@/lib/profile/labels";
import {
  CONTACT_VISIBILITIES,
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
}

function toState(p: StudentProfile): PrivacyState {
  return {
    profile_visibility:
      (p.profile_visibility as ProfileVisibility) ?? "vinuni_only",
    show_email: (p.show_email as ContactVisibility) ?? "hidden",
    show_phone: (p.show_phone as ContactVisibility) ?? "hidden",
  };
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
    state.show_phone !== initial.show_phone;

  const save = useMutation({
    mutationFn: () => {
      const body: UpdateProfileBody = {
        profile_visibility: state.profile_visibility,
        show_email: state.show_email,
        show_phone: state.show_phone,
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
            className="mt-2 flex items-start gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--bg-subtle)] px-3.5 py-2.5 text-xs text-[var(--text-secondary)]"
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
