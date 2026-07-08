"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { ImageSquare, Trash, UploadSimple, ArrowClockwise } from "@phosphor-icons/react";
import { Button, Modal, useToast } from "@/components/ui";
import { SectionCard } from "@/components/settings/section-card";
import { CompanyAvatar } from "@/components/companies/company-avatar";
import { ApiError, organizationApi, type Organization } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

/** Client-side guard mirrors the server contract for a fast, friendly error. */
const MAX_BYTES = 3 * 1024 * 1024;
const ACCEPT = "image/png,image/jpeg,image/webp";
const ALLOWED_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);

interface Props {
  org: Organization;
  /** Apply the server's updated org detail to the parent cache + state. */
  onUpdated: (org: Organization) => void;
  /** Re-fetch the profile after a stale-version (409) conflict. */
  onStale: () => void;
}

/**
 * Partner company-logo control: preview, multipart upload with optimistic
 * `version`, and confirm-modal removal. Server is the source of truth; the
 * client pre-check only spares an obvious round-trip. Friendly, localized,
 * leak-safe error mapping (422 reason / 409 conflict / offline retry).
 */
export function CompanyLogoSection({ org, onUpdated, onStale }: Props) {
  const t = useTranslations("companyProfile");
  const toast = useToast();
  const getMessage = useApiErrorMessage();

  const inputRef = useRef<HTMLInputElement>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmRemove, setConfirmRemove] = useState(false);

  // Object URL lifecycle for the local preview.
  useEffect(() => {
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
      const reason =
        typeof e.details?.reason === "string" ? e.details.reason : undefined;
      if (e.isValidation) {
        if (reason === "empty_file") return t("logoErr.emptyFile");
        if (reason === "file_too_large") return t("logoErr.tooLarge");
        if (reason === "unsupported_image_type")
          return t("logoErr.unsupportedType");
        return e.message || t("logoErr.generic");
      }
      if (e.isConflict) return t("logoErr.conflict");
      if (e.code === "NETWORK_ERROR") return t("logoErr.network");
    }
    return getMessage(e);
  }

  const upload = useMutation({
    mutationFn: (file: File) => organizationApi.uploadLogo(org.id, file, org.version),
    onSuccess: (updated) => {
      onUpdated(updated);
      clearPending();
      setError(null);
      toast.show({ tone: "success", title: t("logoUploadedToast") });
    },
    onError: (e) => {
      setError(mapError(e));
      if (e instanceof ApiError && e.isConflict) onStale();
    },
  });

  const remove = useMutation({
    mutationFn: () => organizationApi.removeLogo(org.id, org.version),
    onSuccess: (updated) => {
      onUpdated(updated);
      setConfirmRemove(false);
      setError(null);
      toast.show({ tone: "success", title: t("logoRemovedToast") });
    },
    onError: (e) => {
      setConfirmRemove(false);
      setError(mapError(e));
      if (e instanceof ApiError && e.isConflict) onStale();
    },
  });

  function clearPending() {
    setPendingFile(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  function onSelect(e: React.ChangeEvent<HTMLInputElement>) {
    setError(null);
    const file = e.target.files?.[0] ?? null;
    if (!file) {
      clearPending();
      return;
    }
    // Fast client pre-check — server still re-validates by magic bytes.
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
  const isNetworkError =
    upload.error instanceof ApiError && upload.error.code === "NETWORK_ERROR";

  return (
    <SectionCard
      title={t("logoTitle")}
      description={t("logoIntro")}
      icon={ImageSquare}
      iconGradient="icon-chip-success"
    >
      <div className="flex flex-col gap-5 sm:flex-row sm:items-start">
        <div className="flex flex-col items-center gap-2">
          <CompanyAvatar
            name={org.display_name}
            logoUrl={previewUrl ?? org.logo_url}
            size="lg"
          />
          <span className="text-xs text-[var(--text-muted)]">
            {pendingFile ? t("logoPreview") : t("logoCurrent")}
          </span>
        </div>

        <div className="min-w-0 flex-1 space-y-3">
          <label
            htmlFor="logo-file"
            className="block text-sm font-semibold text-[var(--text-primary)]"
          >
            {t("logoFileLabel")}
          </label>
          <input
            ref={inputRef}
            id="logo-file"
            type="file"
            accept={ACCEPT}
            onChange={onSelect}
            aria-describedby="logo-hint"
            disabled={busy}
            className="block w-full cursor-pointer text-sm text-[var(--text-secondary)] file:mr-4 file:cursor-pointer file:rounded-lg file:border-0 file:bg-[var(--bg-subtle)] file:px-4 file:py-2 file:text-sm file:font-semibold file:text-[var(--brand-primary)] hover:file:bg-[var(--blue-50)] disabled:cursor-not-allowed disabled:opacity-60"
          />
          <p id="logo-hint" className="text-xs text-[var(--text-muted)]">
            {t("logoHint")}
          </p>

          {error && (
            <p
              role="alert"
              className="flex flex-wrap items-center gap-2 rounded-xl border border-[var(--red-400)]/40 bg-[var(--red-50)] px-3 py-2 text-sm font-medium text-[var(--brand-red)]"
            >
              <span>{error}</span>
              {isNetworkError && pendingFile && (
                <button
                  type="button"
                  onClick={() => upload.mutate(pendingFile)}
                  className="inline-flex items-center gap-1 font-semibold text-[var(--brand-primary)] underline underline-offset-2"
                >
                  <ArrowClockwise aria-hidden weight="bold" className="size-3.5" />
                  {t("logoRetry")}
                </button>
              )}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-3 pt-1">
            {pendingFile && (
              <>
                <Button
                  type="button"
                  variant="primary"
                  loading={upload.isPending}
                  onClick={() => upload.mutate(pendingFile)}
                >
                  <UploadSimple aria-hidden weight="bold" className="size-4" />
                  {t("logoUploadBtn")}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
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
            {!pendingFile && org.logo_url && (
              <Button
                type="button"
                variant="ghost"
                disabled={busy}
                onClick={() => setConfirmRemove(true)}
              >
                <Trash aria-hidden weight="bold" className="size-4" />
                {t("logoRemove")}
              </Button>
            )}
          </div>
        </div>
      </div>

      <Modal
        open={confirmRemove}
        onClose={() => setConfirmRemove(false)}
        title={t("logoRemoveTitle")}
        description={t("logoRemoveBody")}
        size="sm"
        footer={
          <>
            <Button
              variant="ghost"
              disabled={remove.isPending}
              onClick={() => setConfirmRemove(false)}
            >
              {t("logoCancel")}
            </Button>
            <Button
              variant="danger"
              loading={remove.isPending}
              onClick={() => remove.mutate()}
            >
              {t("logoRemoveConfirm")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">
          {t("logoRemoveBody")}
        </p>
      </Modal>
    </SectionCard>
  );
}
