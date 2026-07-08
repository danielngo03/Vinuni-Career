"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import {
  CheckCircle,
  DownloadSimple,
  FilePdf,
  Info,
  WarningCircle,
} from "@phosphor-icons/react";
import { Button, Modal, useToast } from "@/components/ui";
import {
  ApiError,
  cvApi,
  newIdempotencyKey,
  resolveDownloadUrl,
  type CvExport,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

type Phase = "idle" | "starting" | "polling" | "ready" | "failed";

const POLL_INTERVAL_MS = 1500;
const MAX_POLLS = 40;

/**
 * Export a CV version to PDF: POST /cvs/{id}/export, then poll
 * GET /cv-exports/{id} until a signed download URL is ready (API_CONTRACTS).
 * `versionId` is the cv_versions UUID required by the contract; when the server
 * does not expose one yet the modal renders an honest blocked state.
 */
export function CvExportModal({
  open,
  onClose,
  cvId,
  versionId,
}: {
  open: boolean;
  onClose: () => void;
  cvId: string;
  versionId: string | null;
}) {
  const t = useTranslations("cv");
  const tc = useTranslations("common");
  const toast = useToast();
  const apiError = useApiErrorMessage();

  const [phase, setPhase] = useState<Phase>("idle");
  const [exp, setExp] = useState<CvExport | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);
  const pollsRef = useRef(0);

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    clearTimer();
    pollsRef.current = 0;
    setPhase("idle");
    setExp(null);
    setErrorMsg(null);
  }, [clearTimer]);

  useEffect(() => {
    if (!open) reset();
    return () => clearTimer();
  }, [open, reset, clearTimer]);

  const poll = useCallback(
    async (exportId: string) => {
      try {
        const res = await cvApi.getExport(exportId);
        setExp(res);
        if (res.status === "ready" && res.download_url) {
          setPhase("ready");
          return;
        }
        if (res.status === "failed") {
          setPhase("failed");
          setErrorMsg(t("export.failedBody"));
          return;
        }
        pollsRef.current += 1;
        if (pollsRef.current >= MAX_POLLS) {
          setPhase("failed");
          setErrorMsg(t("export.timeout"));
          return;
        }
        timerRef.current = window.setTimeout(
          () => void poll(exportId),
          POLL_INTERVAL_MS,
        );
      } catch (e) {
        setPhase("failed");
        setErrorMsg(apiError(e));
      }
    },
    [t, apiError],
  );

  const start = useCallback(async () => {
    if (!versionId) return;
    clearTimer();
    pollsRef.current = 0;
    setErrorMsg(null);
    setPhase("starting");
    try {
      const created = await cvApi.createExport(cvId, {
        version_id: versionId,
        format: "pdf",
        idempotency_key: newIdempotencyKey(),
      });
      setExp(created);
      if (created.status === "ready" && created.download_url) {
        setPhase("ready");
        return;
      }
      setPhase("polling");
      timerRef.current = window.setTimeout(
        () => void poll(created.export_id),
        POLL_INTERVAL_MS,
      );
    } catch (e) {
      setPhase("failed");
      if (e instanceof ApiError && e.code === "QUOTA_EXCEEDED") {
        setErrorMsg(t("export.quota"));
      } else {
        setErrorMsg(apiError(e));
      }
    }
  }, [cvId, versionId, poll, clearTimer, t, apiError]);

  function handleDownload() {
    if (!exp?.download_url) return;
    window.open(resolveDownloadUrl(exp.download_url), "_blank", "noopener");
    toast.show({ tone: "success", title: t("export.downloadStarted") });
  }

  const busy = phase === "starting" || phase === "polling";

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t("export.title")}
      description={t("export.subtitle")}
      size="sm"
      closeLabel={tc("close")}
      footer={
        phase === "ready" ? (
          <>
            <Button variant="ghost" onClick={onClose}>
              {tc("close")}
            </Button>
            <Button variant="primary" onClick={handleDownload}>
              <DownloadSimple aria-hidden weight="bold" className="size-4" />
              {t("export.download")}
            </Button>
          </>
        ) : (
          <>
            <Button variant="ghost" onClick={onClose} disabled={busy}>
              {tc("cancel")}
            </Button>
            <Button
              variant="primary"
              onClick={start}
              loading={busy}
              disabled={!versionId || busy}
            >
              <FilePdf aria-hidden weight="duotone" className="size-4" />
              {phase === "failed" ? tc("retry") : t("export.start")}
            </Button>
          </>
        )
      }
    >
      {!versionId ? (
        <div className="flex items-start gap-3 rounded-xl bg-[var(--blue-50)] p-4">
          <span className="flex size-6 shrink-0 items-center justify-center rounded-md icon-chip-primary shadow-sm">
            <Info aria-hidden weight="duotone" className="size-3.5 text-white" />
          </span>
          <p className="text-sm text-[var(--text-secondary)]">
            {t("export.versionUnavailable")}
          </p>
        </div>
      ) : phase === "ready" ? (
        <div
          role="status"
          className="flex flex-col items-center gap-3 py-4 text-center"
        >
          <span className="flex size-12 items-center justify-center rounded-2xl icon-chip-success shadow-sm">
            <CheckCircle
              aria-hidden
              weight="duotone"
              className="size-7 text-white"
            />
          </span>
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            {t("export.readyTitle")}
          </p>
          <p className="text-sm text-[var(--text-secondary)]">
            {t("export.readyBody")}
          </p>
        </div>
      ) : phase === "failed" ? (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-xl bg-[var(--red-50)] p-4"
        >
          <span className="flex size-6 shrink-0 items-center justify-center rounded-md icon-chip-danger shadow-sm">
            <WarningCircle aria-hidden weight="duotone" className="size-3.5 text-white" />
          </span>
          <p className="text-sm text-[var(--text-secondary)]">
            {errorMsg ?? t("export.failedBody")}
          </p>
        </div>
      ) : busy ? (
        <div
          role="status"
          className="flex flex-col items-center gap-3 py-6 text-center"
        >
          <span
            aria-hidden
            className="size-8 animate-spin rounded-full border-[3px] border-[var(--brand-primary)] border-t-transparent"
          />
          <p className="text-sm font-medium text-[var(--text-primary)]">
            {t("export.progress")}
          </p>
          <p className="text-xs text-[var(--text-muted)]">
            {t("export.progressHint")}
          </p>
        </div>
      ) : (
        <p className="text-sm text-[var(--text-secondary)]">
          {t("export.intro")}
        </p>
      )}
    </Modal>
  );
}
