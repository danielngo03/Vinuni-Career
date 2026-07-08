"use client";

import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { AddressBook } from "@phosphor-icons/react";
import { Button, Input } from "@/components/ui";
import { SectionCard } from "@/components/settings/section-card";
import { zodResolver } from "@/lib/validation/resolver";
import {
  contactProfileSchema,
  type ContactProfileValues,
} from "@/lib/validation/profile";
import {
  profileApi,
  type StudentProfile,
  type UpdateProfileBody,
} from "@/lib/api";
import { applyFieldErrors } from "@/lib/auth/use-api-error";
import { useProfileMutations } from "./use-profile-mutations";

function nullable(value: string | undefined): string | null {
  const v = (value ?? "").trim();
  return v === "" ? null : v;
}

function toDefaults(p: StudentProfile): ContactProfileValues {
  return {
    phone: p.phone ?? "",
    location_city: p.location_city ?? "",
    location_country: p.location_country ?? "",
  };
}

/** Editable contact details: phone + location. Identity + career content live
 *  elsewhere (account + CVs). */
export function ContactInfoCard({ profile }: { profile: StudentProfile }) {
  const t = useTranslations("profile.contact");
  const tv = useTranslations("profile.validation");
  const tc = useTranslations("common");
  const { setProfile, handleError, notifySaved } = useProfileMutations();

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isDirty },
  } = useForm<ContactProfileValues>({
    resolver: zodResolver(contactProfileSchema(tv)),
    defaultValues: toDefaults(profile),
  });

  // Keep the form in sync when the profile is refetched.
  useEffect(() => {
    reset(toDefaults(profile));
  }, [profile, reset]);

  const save = useMutation({
    mutationFn: (values: ContactProfileValues) => {
      const body: UpdateProfileBody = {
        phone: nullable(values.phone),
        location_city: nullable(values.location_city),
        location_country: nullable(values.location_country),
        expected_version: profile.version,
      };
      return profileApi.updateMine(body);
    },
    onSuccess: (updated) => {
      setProfile(updated);
      reset(toDefaults(updated));
      notifySaved();
    },
    onError: (error) => {
      if (!applyFieldErrors(error, setError)) handleError(error);
    },
  });

  return (
    <SectionCard
      title={t("title")}
      description={t("intro")}
      icon={AddressBook}
      iconGradient="icon-chip-primary"
    >
      <form
        noValidate
        onSubmit={handleSubmit((v) => save.mutate(v))}
        className="space-y-5"
      >
        <Input
          label={t("phone")}
          type="tel"
          autoComplete="tel"
          error={errors.phone?.message}
          {...register("phone")}
        />
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <Input
            label={t("locationCity")}
            autoComplete="address-level2"
            error={errors.location_city?.message}
            {...register("location_city")}
          />
          <Input
            label={t("locationCountry")}
            autoComplete="country-name"
            error={errors.location_country?.message}
            {...register("location_country")}
          />
        </div>

        <div className="flex justify-end">
          <Button
            type="submit"
            variant="primary"
            loading={save.isPending}
            disabled={!isDirty || save.isPending}
          >
            {save.isPending ? tc("saving") : tc("save")}
          </Button>
        </div>
      </form>
    </SectionCard>
  );
}
