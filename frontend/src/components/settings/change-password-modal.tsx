"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslations } from "next-intl";
import { Button, Input, Modal, useToast } from "@/components/ui";
import { accountApi } from "@/lib/api";
import { zodResolver } from "@/lib/validation/resolver";
import {
  changePasswordSchema,
  type ChangePasswordValues,
} from "@/lib/validation/auth";
import { useApiErrorMessage, applyFieldErrors } from "@/lib/auth/use-api-error";
import { FormBanner } from "@/components/auth/form-banner";

export function ChangePasswordModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const t = useTranslations("settings.security");
  const tAuth = useTranslations("auth");
  const tv = useTranslations("auth.validation");
  const tCommon = useTranslations("common");
  const toast = useToast();
  const getMessage = useApiErrorMessage();
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<ChangePasswordValues>({
    resolver: zodResolver(changePasswordSchema(tv)),
    defaultValues: {
      current_password: "",
      new_password: "",
      confirm_password: "",
    },
  });

  function close() {
    reset();
    setFormError(null);
    onClose();
  }

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await accountApi.changePassword({
        current_password: values.current_password,
        new_password: values.new_password,
      });
      toast.show({ tone: "success", title: t("passwordChanged") });
      close();
    } catch (err) {
      if (applyFieldErrors(err, setError)) return;
      setFormError(getMessage(err));
    }
  });

  return (
    <Modal
      open={open}
      onClose={close}
      title={t("changePassword")}
      description={t("changePasswordIntro")}
      size="sm"
      closeLabel={tCommon("close")}
    >
      <form className="space-y-4" onSubmit={onSubmit} noValidate>
        {formError && <FormBanner>{formError}</FormBanner>}
        <Input
          type="password"
          label={t("currentPassword")}
          autoComplete="current-password"
          required
          error={errors.current_password?.message}
          {...register("current_password")}
        />
        <Input
          type="password"
          label={tAuth("newPassword")}
          autoComplete="new-password"
          required
          help={tAuth("passwordHelp")}
          error={errors.new_password?.message}
          {...register("new_password")}
        />
        <Input
          type="password"
          label={tAuth("confirmPassword")}
          autoComplete="new-password"
          required
          error={errors.confirm_password?.message}
          {...register("confirm_password")}
        />
        <div className="flex justify-end gap-3 pt-1">
          <Button type="button" variant="ghost" onClick={close}>
            {tCommon("cancel")}
          </Button>
          <Button type="submit" variant="primary" loading={isSubmitting}>
            {tCommon("save")}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
