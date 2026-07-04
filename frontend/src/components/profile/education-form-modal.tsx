"use client";

import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { Button, Input, Modal, Switch, Textarea } from "@/components/ui";
import { zodResolver } from "@/lib/validation/resolver";
import {
  educationSchema,
  type EducationValues,
} from "@/lib/validation/profile";
import {
  profileApi,
  type EducationBody,
  type EducationItem,
} from "@/lib/api";
import { applyFieldErrors } from "@/lib/auth/use-api-error";
import { useProfileMutations } from "./use-profile-mutations";

function nullable(v: string | undefined): string | null {
  const s = (v ?? "").trim();
  return s === "" ? null : s;
}

function toDefaults(item: EducationItem | null): EducationValues {
  return {
    institution: item?.institution ?? "",
    degree: item?.degree ?? "",
    field_of_study: item?.field_of_study ?? "",
    start_date: item?.start_date ?? "",
    end_date: item?.end_date ?? "",
    is_current: item?.is_current ?? false,
    gpa: item?.gpa != null ? String(item.gpa) : "",
    description: item?.description ?? "",
  };
}

export function EducationFormModal({
  open,
  onClose,
  item,
}: {
  open: boolean;
  onClose: () => void;
  item: EducationItem | null;
}) {
  const t = useTranslations("profile.education");
  const tv = useTranslations("profile.validation");
  const tc = useTranslations("common");
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
  } = useForm<EducationValues>({
    resolver: zodResolver(educationSchema(tv)),
    defaultValues: toDefaults(item),
  });

  useEffect(() => {
    if (open) reset(toDefaults(item));
  }, [open, item, reset]);

  const isCurrent = watch("is_current");

  const save = useMutation({
    mutationFn: (values: EducationValues) => {
      const gpaStr = (values.gpa ?? "").trim();
      const body: EducationBody = {
        institution: values.institution.trim(),
        degree: nullable(values.degree),
        field_of_study: nullable(values.field_of_study),
        start_date: nullable(values.start_date),
        end_date: values.is_current ? null : nullable(values.end_date),
        is_current: values.is_current,
        gpa: gpaStr === "" ? null : Number(gpaStr),
        description: nullable(values.description),
      };
      if (editing) {
        return profileApi.updateEducation(item.id, {
          ...body,
          expected_version: item.version,
        });
      }
      return profileApi.createEducation(body);
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
        <Input
          label={t("institution")}
          required
          error={errors.institution?.message}
          {...register("institution")}
        />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input
            label={t("degree")}
            error={errors.degree?.message}
            {...register("degree")}
          />
          <Input
            label={t("fieldOfStudy")}
            error={errors.field_of_study?.message}
            {...register("field_of_study")}
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
          label={t("gpa")}
          help={t("gpaHelp")}
          inputMode="decimal"
          error={errors.gpa?.message}
          {...register("gpa")}
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
