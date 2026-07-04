"use client";

import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { Button, Input, Modal } from "@/components/ui";
import { zodResolver } from "@/lib/validation/resolver";
import { linkSchema, type LinkValues } from "@/lib/validation/profile";
import { profileApi, type LinkBody, type LinkItem } from "@/lib/api";
import { applyFieldErrors } from "@/lib/auth/use-api-error";
import { useProfileMutations } from "./use-profile-mutations";

function toDefaults(item: LinkItem | null): LinkValues {
  return { label: item?.label ?? "", url: item?.url ?? "" };
}

export function LinkFormModal({
  open,
  onClose,
  item,
}: {
  open: boolean;
  onClose: () => void;
  item: LinkItem | null;
}) {
  const t = useTranslations("profile.links");
  const tv = useTranslations("profile.validation");
  const tc = useTranslations("common");
  const { reloadProfile, handleError, notifySaved } = useProfileMutations();
  const editing = item !== null;

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<LinkValues>({
    resolver: zodResolver(linkSchema(tv)),
    defaultValues: toDefaults(item),
  });

  useEffect(() => {
    if (open) reset(toDefaults(item));
  }, [open, item, reset]);

  const save = useMutation({
    mutationFn: (values: LinkValues) => {
      const body: LinkBody = {
        label: values.label?.trim() ? values.label.trim() : null,
        url: values.url.trim(),
      };
      if (editing) {
        return profileApi.updateLink(item.id, {
          ...body,
          expected_version: item.version,
        });
      }
      return profileApi.createLink(body);
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
          label={t("label")}
          help={t("labelHelp")}
          error={errors.label?.message}
          {...register("label")}
        />
        <Input
          label={t("url")}
          required
          inputMode="url"
          placeholder="https://"
          error={errors.url?.message}
          {...register("url")}
        />
      </form>
    </Modal>
  );
}
