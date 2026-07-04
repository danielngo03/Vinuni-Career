"use client";

import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { Button, Input, Modal, Select } from "@/components/ui";
import { zodResolver } from "@/lib/validation/resolver";
import { skillSchema, type SkillValues } from "@/lib/validation/profile";
import { useProfileLabels } from "@/lib/profile/labels";
import {
  SKILL_CATEGORIES,
  profileApi,
  type SkillBody,
  type SkillItem,
} from "@/lib/api";
import { applyFieldErrors } from "@/lib/auth/use-api-error";
import { useProfileMutations } from "./use-profile-mutations";

const PROFICIENCIES = [1, 2, 3, 4, 5] as const;

function toDefaults(item: SkillItem): SkillValues {
  return {
    name: item.name ?? "",
    category: item.category ?? "",
    proficiency: item.proficiency != null ? String(item.proficiency) : "",
  };
}

/** Edit an existing skill chip (name / category / proficiency). */
export function SkillEditModal({
  open,
  onClose,
  item,
}: {
  open: boolean;
  onClose: () => void;
  item: SkillItem | null;
}) {
  const t = useTranslations("profile.skills");
  const tv = useTranslations("profile.validation");
  const tc = useTranslations("common");
  const labels = useProfileLabels();
  const { reloadProfile, handleError, notifySaved } = useProfileMutations();

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<SkillValues>({
    resolver: zodResolver(skillSchema(tv)),
    defaultValues: { name: "", category: "", proficiency: "" },
  });

  useEffect(() => {
    if (open && item) reset(toDefaults(item));
  }, [open, item, reset]);

  const save = useMutation({
    mutationFn: (values: SkillValues) => {
      if (!item) throw new Error("no item");
      const prof = (values.proficiency ?? "").trim();
      const body: SkillBody = {
        name: values.name.trim(),
        category: values.category ? values.category : null,
        proficiency: prof === "" ? null : Number(prof),
        expected_version: item.version,
      };
      return profileApi.updateSkill(item.id, body);
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
      title={t("editTitle")}
      size="sm"
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
        <Input
          label={t("name")}
          required
          error={errors.name?.message}
          {...register("name")}
        />
        <Select
          label={t("category")}
          error={errors.category?.message}
          options={[
            { value: "", label: t("notSet") },
            ...SKILL_CATEGORIES.map((c) => ({
              value: c,
              label: labels.skillCategory(c),
            })),
          ]}
          {...register("category")}
        />
        <Select
          label={t("proficiency")}
          error={errors.proficiency?.message}
          options={[
            { value: "", label: t("notSet") },
            ...PROFICIENCIES.map((p) => ({
              value: String(p),
              label: labels.proficiency(p),
            })),
          ]}
          {...register("proficiency")}
        />
      </form>
    </Modal>
  );
}
