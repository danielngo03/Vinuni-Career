"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { CircleNotch } from "@phosphor-icons/react";
import { Button, Input, Modal, useToast } from "@/components/ui";
import { accountApi } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { FormBanner } from "@/components/auth/form-banner";

/**
 * Two-factor (TOTP) enrollment. Fetches a setup secret, shows it for manual
 * entry into an authenticator app, then verifies a 6-digit code. We surface the
 * secret as text (not a provider-rendered QR) to avoid extra dependencies and
 * never expose internal status codes.
 */
export function TotpModal({
  open,
  onClose,
  onEnabled,
}: {
  open: boolean;
  onClose: () => void;
  onEnabled: () => void;
}) {
  const t = useTranslations("settings.security");
  const tCommon = useTranslations("common");
  const toast = useToast();
  const getMessage = useApiErrorMessage();
  const started = useRef(false);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  const setup = useMutation({
    mutationFn: () => accountApi.totpSetup(),
  });

  const verify = useMutation({
    mutationFn: (c: string) => accountApi.totpVerify({ code: c }),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("totpEnabled") });
      onEnabled();
      onClose();
    },
    onError: (e) => setError(getMessage(e)),
  });

  // Fetch the setup secret once when the modal opens.
  useEffect(() => {
    if (open && !started.current) {
      started.current = true;
      setup.mutate();
    }
    if (!open) {
      started.current = false;
      setCode("");
      setError(null);
    }
  }, [open, setup]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t("enableTotp")}
      description={t("totpIntro")}
      size="sm"
      closeLabel={tCommon("close")}
    >
      {setup.isPending ? (
        <div className="flex flex-col items-center gap-3 py-6 text-center">
          <CircleNotch
            aria-hidden
            className="size-7 animate-spin text-[var(--brand-primary)]"
          />
          <p className="text-sm text-[var(--text-secondary)]">
            {tCommon("loading")}
          </p>
        </div>
      ) : setup.isError ? (
        <div className="space-y-4">
          <FormBanner>{getMessage(setup.error)}</FormBanner>
          <Button variant="secondary" fullWidth onClick={() => setup.mutate()}>
            {tCommon("retry")}
          </Button>
        </div>
      ) : setup.data ? (
        <div className="space-y-4">
          <div>
            <p className="text-sm text-[var(--text-secondary)]">
              {t("totpSecretLabel")}
            </p>
            <code className="mt-1 block break-all rounded-lg border border-[var(--border-default)] bg-[var(--bg-subtle)] px-3 py-2 font-mono text-sm tracking-wider text-[var(--text-primary)]">
              {setup.data.secret}
            </code>
          </div>
          {error && <FormBanner>{error}</FormBanner>}
          <Input
            label={t("totpCodeLabel")}
            inputMode="numeric"
            autoComplete="one-time-code"
            placeholder="000000"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
          />
          <div className="flex justify-end gap-3">
            <Button variant="ghost" onClick={onClose}>
              {tCommon("cancel")}
            </Button>
            <Button
              variant="primary"
              loading={verify.isPending}
              disabled={code.length !== 6}
              onClick={() => {
                setError(null);
                verify.mutate(code);
              }}
            >
              {t("totpVerify")}
            </Button>
          </div>
        </div>
      ) : null}
    </Modal>
  );
}
