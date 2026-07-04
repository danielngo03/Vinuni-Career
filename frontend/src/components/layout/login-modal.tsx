"use client";

import { useTranslations } from "next-intl";
import { Modal } from "@/components/ui";
import { useRouter } from "@/i18n/navigation";
import { useUiStore } from "@/stores/ui-store";
import { useAuthStore } from "@/stores/auth-store";
import { LoginForm } from "@/components/auth/login-form";

/**
 * Intent-preserving login modal. Opened by guest actions that require auth.
 * On success it closes and resumes the captured intent (returnTo), so the user
 * lands exactly where they were headed. Focus trap + Escape come from Modal.
 */
export function LoginModal() {
  const t = useTranslations("auth");
  const { loginModalOpen, authIntent, closeLoginModal } = useUiStore();
  const router = useRouter();

  const title = authIntent?.label
    ? `${t("intentPrefix")} ${authIntent.label}`
    : t("loginTitle");

  function handleSuccess() {
    closeLoginModal();
    const persona = useAuthStore.getState().user?.persona ?? "student";
    router.replace(authIntent?.returnTo || `/${persona}/dashboard`);
  }

  return (
    <Modal
      open={loginModalOpen}
      onClose={closeLoginModal}
      title={title}
      description={t("loginSubtitle")}
      size="sm"
      closeLabel={t("closeLabel")}
    >
      <LoginForm compact onSuccess={handleSuccess} />
    </Modal>
  );
}
