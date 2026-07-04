"use client";

import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { Button, Input, Modal, Select, Switch, Textarea } from "@/components/ui";
import { zodResolver } from "@/lib/validation/resolver";
import {
  experienceSchema,
  type ExperienceValues,
} from "@/lib/validation/profile";
import { useProfileLabels } from "@/lib/profile/labels";
import {
  PROFILE_EMPLOYMENT_TYPES,
  profileApi,
  type ExperienceBody,
  type ExperienceItem,
} from "@/lib/api";
import { applyFieldErrors } from "@/lib/auth/use-api-error";
import { useProfileMutations } from "./use-profile-mutations";

function nullable(v: string | undefined): string | null {
  const s = (v ?? "").trim();
  return s === "" ? null : s;
}

function toDefaults(item: ExperienceItem | null): ExperienceValues {
  return {
    company_name: item?.company_name ?? "",
    title: item?.title ?? "",
    employment_type: item?.employment_type ?? "",
    location: item?.location ?? "",
    start_date: item?.start_date ?? "",
    end_date: item?.end_date ?? "",
    is_current: item?.is_current ?? false,
    skills_used: item?.skills_used?.join(", ") ?? "",
    description: item?.description ?? "",
  };
}

export function ExperienceFormModal({
  open,
  onClose,
  item,
}: {
  open: boolean;
  onClose: () => void;
  item: ExperienceItem | null;
}) {
  const t = useTranslations("profile.experience");
  const tv = useTranslations("profile.validation");
  const tc = useTranslations("common");
  const labels = useProfileLabels();
  const { reloadProfile, handleError, notifySaved } = useProfileMutations();
  const editing = item !== null;

  const {
    register,
    handleSubmit,
    reset,
    watch,
    setValue,
    setError,
    formState: { errors },
  } = useForm<ExperienceValues>({
    resolver: zodResolver(experienceSchema(tv)),
    defaultValues: toDefaults(item),
  });

  useEffect(() => {
    if (open) reset(toDefaults(item));
  }, [open, item, reset]);

  const isCurrent = watch("is_current");

  const save = useMutation({
    mutationFn: (values: ExperienceValues) => {
      const skills = (values.skills_used ?? "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const body: ExperienceBody = {
        company_name: values.company_name.trim(),
        title: values.title.trim(),
        employment_type: nullable(values.employment_type),
        location: nullable(values.location),
        start_date: nullable(values.start_date),
        end_date: values.is_current ? null : nullable(values.end_date),
        is_current: values.is_current,
        skills_used: skills,
        description: nullable(values.description),
      };
      if (editing) {
        return profileApi.updateExperience(item.id, {
          ...body,
          expected_version: item.version,
        });
      }
      return profileApi.createExperience(body);
    },
    onSuccess: () => {
      reloadProfile();
      notifySaved();
      onClose();
    },
    onError: (error) => {
      if (handleError(error)) onClose();
      else applyFieldErrors(error, setError);
    },
  });

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editing ? t("editTitle") : t("addTitle")}
      size="md"
      closeLabel={tc("close")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={save.isPending}>
            {tc("cancel")}
          </Button>
          <Button
            variant="primary"
            loading={save.isPending}
            onClick={handleSubmit((v) => save.mutate(v))}
          >
            {tc("save")}
          </Button>
        </>
      }
    >
      <form
        noValidate
        onSubmit={handleSubmit((v) => save.mutate(v))}
        className="space-y-4"
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input
            label={t("company")}
            required
            error={errors.company_name?.message}
            {...register("company_name")}
          />
          <Input
            label={t("jobTitle")}
            required
            error={errors.title?.message}
            {...register("title")}
          />
          <Select
            label={t("employmentType")}
            error={errors.employment_type?.message}
            options={[
              { value: "", label: t("notSet") },
              ...PROFILE_EMPLOYMENT_TYPES.map((e) => ({
                value: e,
                label: labels.employment(e),
              })),
            ]}
            {...register("employment_type")}
          />
          <Input
            label={t("location")}
            error={errors.location?.message}
            {...register("location")}
          />
          <Input
            label={t("startDate")}
            type="date"
            error={errors.start_date?.message}
            {...register("start_date")}
          />
          <Input
            label={t("endDate")}
            type="date"
            disabled={isCurrent}
            error={errors.end_date?.message}
            {...register("end_date")}
          />
        </div>
        <Switch
          label={t("isCurrent")}
          checked={isCurrent}
          onCheckedChange={(v) => {
            setValue("is_current", v, { shouldDirty: true });
            if (v) setValue("end_date", "");
          }}
        />
        <Input
          label={t("skillsUsed")}
          help={t("skillsUsedHelp")}
          error={errors.skills_used?.message}
          {...register("skills_used")}
        />
        <Textarea
          label={t("description")}
          rows={3}
          error={errors.description?.message}
          {...register("description")}
        />
      </form>
    </Modal>
  );
}
