"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { ImageUp, RefreshCw, Trash2, UploadCloud } from "lucide-react";
import { Button, Modal, useToast } from "@/components/ui";
import { CompanyAvatar } from "@/components/companies/company-avatar";
import { ApiError, organizationApi } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

/** Client-side guard mirrors the server contract for a fast, friendly error. */
const MAX_BYTES = 3 * 1024 * 1024;
const ACCEPT = "image/png,image/jpeg,image/webp";
const ALLOWED_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);

/**
 * Company logo control (v10) — preview, multipart upload with optimistic
 * `version`, and confirm-modal removal. The logo is a COSMETIC asset (no
 * university review), so it writes to the live org immediately via
 * `organizationApi`. On any success we ask the parent to refetch the profile
 * (the shared org `version` moves), keeping the whole surface consistent.
 */
export function CompanyLogoCard({
  orgId,
  displayName,
  logoUrl,
  version,
  disabled = false,
  onChanged,
}: {
  orgId: string;
  displayName: string;
  logoUrl: string | null;
  version: number;
  /** Read-only when the member lacks `organizations:update`. */
  disabled?: boolean;
  /** Refetch the profile after a logo write (org version moved). */
  onChanged: () => void;
}) {
  const t = useTranslations("companyProfile");
  const toast = useToast();
  const getMessage = useApiErrorMessage();

  const inputRef = React.useRef<HTMLInputElement>(null);
  const [pendingFile, setPendingFile] = React.useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [confirmRemove, setConfirmRemove] = React.useState(false);

  React.useEffect(() => {
    if (!pendingFile) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(pendingFile);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [pendingFile]);

  function mapError(e: unknown): string {
    if (e instanceof ApiError) {
      const reason = typeof e.details?.reason === "string" ? e.details.reason : undefined;
      if (e.isValidation) {
        if (reason === "empty_file") return t("logoErr.emptyFile");
        if (reason === "file_too_large") return t("logoErr.tooLarge");
        if (reason === "unsupported_image_type") return t("logoErr.unsupportedType");
        return e.message || t("logoErr.generic");
      }
      if (e.isConflict) return t("logoErr.conflict");
      if (e.code === "NETWORK_ERROR") return t("logoErr.network");
    }
    return getMessage(e);
  }

  function clearPending() {
    setPendingFile(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  const upload = useMutation({
    mutationFn: (file: File) => organizationApi.uploadLogo(orgId, file, version),
    onSuccess: () => {
      clearPending();
      setError(null);
      toast.show({ tone: "success", title: t("logoUploadedToast") });
      onChanged();
    },
    onError: (e) => {
      setError(mapError(e));
      if (e instanceof ApiError && e.isConflict) onChanged();
    },
  });

  const remove = useMutation({
    mutationFn: () => organizationApi.removeLogo(orgId, version),
    onSuccess: () => {
      setConfirmRemove(false);
      setError(null);
      toast.show({ tone: "success", title: t("logoRemovedToast") });
      onChanged();
    },
    onError: (e) => {
      setConfirmRemove(false);
      setError(mapError(e));
      if (e instanceof ApiError && e.isConflict) onChanged();
    },
  });

  function onSelect(e: React.ChangeEvent<HTMLInputElement>) {
    setError(null);
    const file = e.target.files?.[0] ?? null;
    if (!file) {
      clearPending();
      return;
    }
    if (!ALLOWED_TYPES.has(file.type)) {
      setError(t("logoErr.unsupportedType"));
      clearPending();
      return;
    }
    if (file.size > MAX_BYTES) {
      setError(t("logoErr.tooLarge"));
      clearPending();
      return;
    }
    if (file.size === 0) {
      setError(t("logoErr.emptyFile"));
      clearPending();
      return;
    }
    setPendingFile(file);
  }

  const busy = upload.isPending || remove.isPending;
  const isNetworkError = upload.error instanceof ApiError && upload.error.code === "NETWORK_ERROR";

  return (
    <div className="flex flex-col gap-5 sm:flex-row sm:items-start">
      <div className="flex flex-col items-center gap-2">
        <CompanyAvatar name={displayName} logoUrl={previewUrl ?? logoUrl} size="lg" />
        <span className="type-caption text-muted-foreground">
          {pendingFile ? t("logoPreview") : t("logoCurrent")}
        </span>
      </div>

      <div className="min-w-0 flex-1 space-y-3">
        <div className="flex items-center gap-2">
          <ImageUp aria-hidden className="size-4 text-muted-foreground" strokeWidth={1.8} />
          <p className="type-small font-medium text-foreground">{t("logoFileLabel")}</p>
        </div>
        {disabled ? (
          <p className="type-small text-muted-foreground">{t("logoReadOnly")}</p>
        ) : (
          <>
            <input
              ref={inputRef}
              id="logo-file"
              type="file"
              accept={ACCEPT}
              onChange={onSelect}
              aria-describedby="logo-hint"
              disabled={busy}
              className="block w-full cursor-pointer text-sm text-muted-foreground file:mr-4 file:cursor-pointer file:rounded-lg file:border-0 file:bg-[var(--bg-subtle)] file:px-4 file:py-2 file:text-sm file:font-semibold file:text-foreground hover:file:bg-[var(--bg-muted)] disabled:cursor-not-allowed disabled:opacity-60"
            />
            <p id="logo-hint" className="type-caption text-muted-foreground">
              {t("logoHint")}
            </p>
          </>
        )}

        {error && (
          <p
            role="alert"
            className="flex flex-wrap items-center gap-2 rounded-lg border border-[var(--content-danger)]/30 bg-[var(--content-danger-soft)] px-3 py-2 text-[0.8125rem] font-medium text-[var(--content-danger)]"
          >
            <span>{error}</span>
            {isNetworkError && pendingFile && (
              <button
                type="button"
                onClick={() => upload.mutate(pendingFile)}
                className="inline-flex items-center gap-1 font-semibold text-foreground underline underline-offset-2"
              >
                <RefreshCw aria-hidden className="size-3.5" strokeWidth={2} />
                {t("logoRetry")}
              </button>
            )}
          </p>
        )}

        {!disabled && (
          <div className="flex flex-wrap items-center gap-2 pt-1">
            {pendingFile && (
              <>
                <Button
                  type="button"
                  variant="primary"
                  size="sm"
                  loading={upload.isPending}
                  onClick={() => upload.mutate(pendingFile)}
                >
                  <UploadCloud aria-hidden className="size-4" strokeWidth={1.9} />
                  {t("logoUploadBtn")}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={busy}
                  onClick={() => {
                    clearPending();
                    setError(null);
                  }}
                >
                  {t("logoCancel")}
                </Button>
              </>
            )}
            {!pendingFile && logoUrl && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={() => setConfirmRemove(true)}
              >
                <Trash2 aria-hidden className="size-4" strokeWidth={1.8} />
                {t("logoRemove")}
              </Button>
            )}
          </div>
        )}
      </div>

      <Modal
        open={confirmRemove}
        onClose={() => setConfirmRemove(false)}
        title={t("logoRemoveTitle")}
        description={t("logoRemoveBody")}
        size="sm"
        footer={
          <>
            <Button variant="ghost" disabled={remove.isPending} onClick={() => setConfirmRemove(false)}>
              {t("logoCancel")}
            </Button>
            <Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>
              {t("logoRemoveConfirm")}
            </Button>
          </>
        }
      >
        <p className="type-small text-muted-foreground">{t("logoRemoveBody")}</p>
      </Modal>
    </div>
  );
}
