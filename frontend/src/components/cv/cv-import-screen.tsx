"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { ArrowLeft } from "@phosphor-icons/react";
import { useRouter } from "@/i18n/navigation";
import { useToast } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { CvQuotaModal } from "./cv-quota-modal";
import { PickStep } from "./import-steps/pick-step";
import { PreviewStep } from "./import-steps/preview-step";
import { ProcessingStep } from "./import-steps/processing-step";
import { CalmStatus } from "./import-steps/calm-status";
import { FailedStep } from "./import-steps/failed-step";
import { ReviewStep } from "./import-steps/review-step";
import {
  ApiError,
  cvIngestionApi,
  newIdempotencyKey,
  parseCvQuotaError,
  parseFactConfirmationRequiredError,
  rememberImportOrigin,
  TERMINAL_INGESTION_STATUSES,
  type Ingestion,
  type UploadPreview,
  type CvQuotaInfo,
  type ImportIngestionBody,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

type Phase =
  | "pick"
  | "uploading"
  | "preview"
  | "processing"
  | "review"
  | "failed"
  | "importing";

const MAX_BYTES = 50 * 1024 * 1024;
const ACCEPTED_EXT = ["pdf", "doc", "docx", "txt", "png", "jpg", "jpeg", "webp"];
const POLL_INTERVAL_MS = 1400;
const MAX_POLLS = 60;

export function CvImportScreen() {
  const t = useTranslations("cv.import");
  const tFail = useTranslations("cv.import.failure");
  const router = useRouter();
  const toast = useToast();
  const apiError = useApiErrorMessage();

  const [phase, setPhase] = useState<Phase>("pick");
  const [dragOver, setDragOver] = useState(false);
  const [preview, setPreview] = useState<UploadPreview | null>(null);
  const [ingestion, setIngestion] = useState<Ingestion | null>(null);
  const [titleDraft, setTitleDraft] = useState<string>("");
  const [clientError, setClientError] = useState<string | null>(null);
  const [fatalError, setFatalError] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);
  const [quotaInfo, setQuotaInfo] = useState<CvQuotaInfo | null>(null);
  // Paths the backend's per-field confirmation gate rejected as undecided
  // (422 fact_confirmation_required) — the review screen re-highlights these.
  const [undecidedPaths, setUndecidedPaths] = useState<string[]>([]);

  const timerRef = useRef<number | null>(null);
  const pollsRef = useRef(0);
  const seenScannedRef = useRef(false);
  const retryRef = useRef<() => void>(() => {});

  const isOffline = useCallback(
    (e: unknown): e is ApiError =>
      e instanceof ApiError && e.code === "NETWORK_ERROR",
    [],
  );

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => () => clearTimer(), [clearTimer]);

  const reset = useCallback(() => {
    clearTimer();
    pollsRef.current = 0;
    seenScannedRef.current = false;
    setPhase("pick");
    setPreview(null);
    setIngestion(null);
    setTitleDraft("");
    setClientError(null);
    setFatalError(null);
    setOffline(false);
  }, [clearTimer]);

  /* ----------------------------- Upload (preview-first) ----------------------------- */

  const handleFile = useCallback(
    async (file: File) => {
      setClientError(null);
      const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
      if (!ACCEPTED_EXT.includes(ext)) {
        setClientError(t("errInvalidType"));
        return;
      }
      if (file.size > MAX_BYTES) {
        setClientError(t("errTooLarge"));
        return;
      }
      setPhase("uploading");
      setOffline(false);
      setFatalError(null);
      try {
        const result = await cvIngestionApi.createUpload(
          file,
          newIdempotencyKey(),
        );
        setPreview(result);
        setTitleDraft(result.filename.replace(/\.[^.]+$/, ""));
        setPhase("preview");
      } catch (e) {
        const quota = parseCvQuotaError(e);
        if (quota) {
          setQuotaInfo(quota);
          setPhase("pick");
          return;
        }
        if (isOffline(e)) {
          retryRef.current = () => void handleFile(file);
          setOffline(true);
          setPhase("failed");
          return;
        }
        setFatalError(apiError(e));
        setPhase("failed");
      }
    },
    [t, apiError, isOffline],
  );

  /* ----------------------------- Ingest + poll ----------------------------- */

  const importToCv = useCallback(
    async (ing: Ingestion, body: ImportIngestionBody) => {
      if (!preview) return;
      setPhase("importing");
      setUndecidedPaths([]);
      try {
        const cv = await cvIngestionApi.importIngestion(ing.ingestion_id, {
          ...body,
          idempotency_key: newIdempotencyKey(),
        });
        rememberImportOrigin(cv.id, {
          documentId: preview.document_id,
          previewUrl: preview.preview_url,
          filename: preview.filename,
          contentType: preview.content_type,
          pageCount: preview.page_count,
        });
        toast.show({ tone: "success", title: t("importedToast") });
        router.push(`/student/cv/${cv.id}`);
      } catch (e) {
        const quota = parseCvQuotaError(e);
        if (quota) {
          setQuotaInfo(quota);
          setPhase("review");
          return;
        }
        if (isOffline(e)) {
          retryRef.current = () => void importToCv(ing, body);
          setOffline(true);
          setPhase("failed");
          return;
        }
        const undecided = parseFactConfirmationRequiredError(e);
        if (undecided) {
          // Server-side re-check found needs_review fields without a decision
          // (e.g. the ingestion changed between load and import). Highlight
          // exactly those fields rather than a generic error.
          setUndecidedPaths(undecided);
          toast.show({ tone: "error", title: t("confirmFactsNote") });
          setPhase("review");
          return;
        }
        toast.show({ tone: "error", title: apiError(e) });
        // Return to the review screen rather than a dead-end failure page —
        // the student's edits/decisions are preserved so they can retry.
        setPhase("review");
      }
    },
    [preview, t, toast, router, apiError, isOffline],
  );

  /**
   * A terminal, importable ingestion (`ready`/`needs_review`) always routes to
   * the explicit review screen — it never auto-imports
   * (`docs/CV_INGESTION_EXTRACTION_SPEC.md` §2 "Review Screen").
   */
  const applyTerminal = useCallback((ing: Ingestion) => {
    setIngestion(ing);
    setPhase(ing.status === "failed" ? "failed" : "review");
  }, []);

  const poll = useCallback(
    async (ingestionId: string) => {
      try {
        const ing = await cvIngestionApi.getIngestion(ingestionId);
        setIngestion(ing);
        if (ing.status === "reading_scanned") seenScannedRef.current = true;
        if (TERMINAL_INGESTION_STATUSES.has(ing.status)) {
          applyTerminal(ing);
          return;
        }
        pollsRef.current += 1;
        if (pollsRef.current >= MAX_POLLS) {
          setFatalError(t("timeout"));
          setPhase("failed");
          return;
        }
        timerRef.current = window.setTimeout(
          () => void poll(ingestionId),
          POLL_INTERVAL_MS,
        );
      } catch (e) {
        if (isOffline(e)) {
          retryRef.current = () => {
            setOffline(false);
            setPhase("processing");
            void poll(ingestionId);
          };
          setOffline(true);
          setPhase("failed");
          return;
        }
        setFatalError(apiError(e));
        setPhase("failed");
      }
    },
    [t, apiError, isOffline, applyTerminal],
  );

  const startIngest = useCallback(async () => {
    if (!preview) return;
    setPhase("processing");
    setOffline(false);
    setFatalError(null);
    pollsRef.current = 0;
    seenScannedRef.current = false;
    try {
      const ing = await cvIngestionApi.startIngestion(
        preview.document_id,
        newIdempotencyKey(),
      );
      setIngestion(ing);
      if (ing.status === "reading_scanned") seenScannedRef.current = true;
      if (TERMINAL_INGESTION_STATUSES.has(ing.status)) {
        applyTerminal(ing);
        return;
      }
      timerRef.current = window.setTimeout(
        () => void poll(ing.ingestion_id),
        POLL_INTERVAL_MS,
      );
    } catch (e) {
      if (isOffline(e)) {
        retryRef.current = () => void startIngest();
        setOffline(true);
        setPhase("failed");
        return;
      }
      setFatalError(apiError(e));
      setPhase("failed");
    }
  }, [preview, poll, apiError, isOffline, applyTerminal]);

  /* ----------------------------- Drag-drop dropzone ----------------------------- */

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) void handleFile(f);
  }

  /* ----------------------------- Render helpers ----------------------------- */

  const backLink = (
    <button
      type="button"
      onClick={() => router.push("/student/cv")}
      className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-sm font-medium text-[var(--text-secondary)] outline-none hover:text-[var(--brand-primary)] focus-visible:underline"
    >
      <ArrowLeft aria-hidden weight="bold" className="size-4" />
      {t("backToStudio")}
    </button>
  );

  return (
    <div>
      <div className="mb-4">{backLink}</div>
      <PageHeader title={t("title")} description={t("subtitle")} />

      {phase === "pick" && (
        <PickStep
          dragOver={dragOver}
          onDragState={setDragOver}
          onDrop={onDrop}
          onFile={handleFile}
          clientError={clientError}
          onCreateFromTemplate={() => router.push("/student/cv?create=1")}
        />
      )}

      {phase === "uploading" && (
        <CalmStatus title={t("uploading")} hint={t("uploadingHint")} />
      )}

      {phase === "preview" && preview && (
        <PreviewStep
          preview={preview}
          onUse={startIngest}
          onAnother={reset}
        />
      )}

      {phase === "processing" && (
        <ProcessingStep
          ingestion={ingestion}
          seenScanned={seenScannedRef.current}
        />
      )}

      {phase === "importing" && (
        <CalmStatus title={t("importing")} hint={t("importingHint")} />
      )}

      {phase === "failed" && (
        <FailedStep
          offline={offline}
          fatalError={fatalError}
          ingestion={ingestion}
          tFail={tFail}
          onRetry={() => {
            setOffline(false);
            retryRef.current();
          }}
          onAnother={reset}
          onCreateFromTemplate={() => router.push("/student/cv?create=1")}
        />
      )}

      {phase === "review" && ingestion && preview && (
        <ReviewStep
          ingestion={ingestion}
          preview={preview}
          titleDraft={titleDraft}
          onTitleChange={setTitleDraft}
          onImport={(body) => void importToCv(ingestion, body)}
          onKeepOriginal={() => router.push("/student/cv")}
          onUploadAnother={reset}
          importing={false}
          forcePendingPaths={undecidedPaths}
        />
      )}

      <CvQuotaModal
        open={quotaInfo !== null}
        info={quotaInfo}
        onClose={() => setQuotaInfo(null)}
        onGoToLibrary={() => {
          setQuotaInfo(null);
          router.push("/student/cv");
        }}
      />
    </div>
  );
}
