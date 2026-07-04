"use client";

import { useTranslations } from "next-intl";
import {
  ArrowSquareOut,
  FilePdf,
  FileDoc,
  FileText,
  Image as ImageIcon,
  FileArrowDown,
} from "@phosphor-icons/react";
import { resolveDownloadUrl, type UploadPreview } from "@/lib/api";
import { cn } from "@/lib/utils";

type PreviewKind = "pdf" | "image" | "doc" | "text" | "other";

function kindOf(p: { content_type: string; filename: string }): PreviewKind {
  const ct = (p.content_type || "").toLowerCase();
  const ext = p.filename.split(".").pop()?.toLowerCase() ?? "";
  if (ct.includes("pdf") || ext === "pdf") return "pdf";
  if (ct.startsWith("image/") || ["png", "jpg", "jpeg", "webp", "gif"].includes(ext))
    return "image";
  if (ct.includes("word") || ["doc", "docx"].includes(ext)) return "doc";
  if (ct.startsWith("text/") || ext === "txt") return "text";
  return "other";
}

export function formatBytes(bytes: number): string {
  if (!bytes || bytes < 0) return "0 KB";
  const kb = bytes / 1024;
  if (kb < 1024) return `${Math.max(1, Math.round(kb))} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

const KIND_ICON: Record<PreviewKind, typeof FilePdf> = {
  pdf: FilePdf,
  image: ImageIcon,
  doc: FileDoc,
  text: FileText,
  other: FileText,
};

/**
 * Faithful preview of the ORIGINAL uploaded document, shown BEFORE any
 * extraction (`docs/CV_INGESTION_EXTRACTION_SPEC.md` §2). PDFs use the browser's
 * native viewer (zoom/scroll built in); images render directly; DOC/DOCX/other
 * show a metadata card and a "preview after processing" note. Every variant
 * offers a keyboard-reachable "open in a new tab" escape hatch.
 */
export function CvOriginalPreview({
  preview,
  className,
  /** Compact metadata-only header (used in the review pane's left column). */
  frameless = false,
}: {
  preview: UploadPreview;
  className?: string;
  frameless?: boolean;
}) {
  const t = useTranslations("cv.import");
  const kind = kindOf(preview);
  const Icon = KIND_ICON[kind];
  const url = preview.preview_url ? resolveDownloadUrl(preview.preview_url) : null;

  const meta = (
    <div className="flex min-w-0 items-center gap-2.5">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg icon-chip-primary shadow-sm">
        <Icon aria-hidden weight="duotone" className="size-5 text-white" />
      </span>
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-[var(--text-primary)]" title={preview.filename}>
          {preview.filename}
        </p>
        <p className="text-xs text-[var(--text-muted)]">
          {formatBytes(preview.size)}
          {preview.page_count
            ? ` · ${t("pages", { count: preview.page_count })}`
            : ""}
        </p>
      </div>
    </div>
  );

  return (
    <div className={cn("flex min-h-0 flex-col", className)}>
      <div className="flex items-center justify-between gap-2 border-b border-[var(--glass-border)] px-3 py-2">
        {meta}
        {url && (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-semibold text-[var(--brand-primary)] outline-none hover:underline focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
          >
            <ArrowSquareOut aria-hidden weight="bold" className="size-3.5" />
            {t("openOriginal")}
          </a>
        )}
      </div>

      <div
        className={cn(
          "min-h-0 flex-1",
          frameless ? "" : "bg-[var(--glass-surface-light)]",
        )}
      >
        {!url ? (
          <ProcessingPlaceholder label={t("previewAfterProcessing")} Icon={Icon} />
        ) : kind === "pdf" ? (
          <object
            data={url}
            type="application/pdf"
            aria-label={t("originalPreviewLabel", { name: preview.filename })}
            className="h-full min-h-[420px] w-full"
          >
            <FallbackLink url={url} label={t("openOriginal")} note={t("pdfFallback")} />
          </object>
        ) : kind === "image" ? (
          <div className="flex h-full min-h-[420px] items-center justify-center overflow-auto p-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={url}
              alt={t("originalPreviewLabel", { name: preview.filename })}
              className="max-h-full max-w-full rounded-md border border-[var(--border-default)] bg-white object-contain shadow-[var(--shadow-sm)]"
            />
          </div>
        ) : (
          <ProcessingPlaceholder
            label={t("previewAfterProcessing")}
            note={kind === "doc" ? t("docNote") : undefined}
            Icon={Icon}
            actionUrl={url}
            actionLabel={t("downloadOriginal")}
          />
        )}
      </div>
    </div>
  );
}

function ProcessingPlaceholder({
  label,
  note,
  Icon,
  actionUrl,
  actionLabel,
}: {
  label: string;
  note?: string;
  Icon: typeof FilePdf;
  actionUrl?: string;
  actionLabel?: string;
}) {
  return (
    <div className="flex h-full min-h-[420px] flex-col items-center justify-center gap-3 p-6 text-center">
      <span className="flex size-14 items-center justify-center rounded-2xl icon-chip-primary shadow-[var(--shadow-sm)]">
        <Icon aria-hidden weight="duotone" className="size-7 text-white" />
      </span>
      <p className="max-w-xs text-sm font-medium text-[var(--text-secondary)]">{label}</p>
      {note && <p className="max-w-xs text-xs text-[var(--text-muted)]">{note}</p>}
      {actionUrl && actionLabel && (
        <a
          href={actionUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] backdrop-blur-md px-3 py-1.5 text-xs font-semibold text-[var(--text-primary)] outline-none hover:border-[var(--brand-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
        >
          <FileArrowDown aria-hidden weight="bold" className="size-4" />
          {actionLabel}
        </a>
      )}
    </div>
  );
}

function FallbackLink({
  url,
  label,
  note,
}: {
  url: string;
  label: string;
  note: string;
}) {
  return (
    <div className="flex h-full min-h-[420px] flex-col items-center justify-center gap-3 p-6 text-center">
      <p className="max-w-xs text-sm text-[var(--text-secondary)]">{note}</p>
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] backdrop-blur-md px-3 py-1.5 text-sm font-semibold text-[var(--brand-primary)] outline-none hover:border-[var(--brand-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
      >
        <ArrowSquareOut aria-hidden weight="bold" className="size-4" />
        {label}
      </a>
    </div>
  );
}
