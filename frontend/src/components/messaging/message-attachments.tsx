"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import {
  DownloadSimple,
  File as FileIcon,
  FilePdf,
  FileZip,
  ImageBroken,
  CircleNotch,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { messagingApi, type MessagingAttachment } from "@/lib/api";
import { formatBytes } from "./attachment-api";

/** Render a message's bound attachments: inline images + downloadable file chips. */
export function MessageAttachments({
  attachments,
  mine,
}: {
  attachments: MessagingAttachment[];
  mine: boolean;
}) {
  if (!attachments || attachments.length === 0) return null;
  const images = attachments.filter((a) => a.kind === "image");
  const files = attachments.filter((a) => a.kind !== "image");

  return (
    <div className="mt-1.5 flex flex-col gap-1.5">
      {images.length > 0 && (
        <div
          className={cn(
            "flex flex-wrap gap-1.5",
            mine ? "justify-end" : "justify-start",
          )}
        >
          {images.map((a) => (
            <AttachmentImage key={a.id} attachment={a} />
          ))}
        </div>
      )}
      {files.map((a) => (
        <AttachmentFile key={a.id} attachment={a} mine={mine} />
      ))}
    </div>
  );
}

/* --------------------------------- Image ---------------------------------- */

function AttachmentImage({ attachment }: { attachment: MessagingAttachment }) {
  const t = useTranslations("messaging");
  const [src, setSrc] = useState<string | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    let url: string | null = null;
    let cancelled = false;
    setState("loading");
    messagingApi
      .downloadAttachment(attachment.id)
      .then((blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setSrc(url);
        setState("ready");
      })
      .catch(() => {
        if (!cancelled) setState("error");
      });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [attachment.id]);

  if (state === "error") {
    return (
      <span className="flex h-24 w-32 flex-col items-center justify-center gap-1 rounded-lg bg-[var(--bg-muted)] text-[var(--text-muted)]">
        <ImageBroken aria-hidden weight="duotone" className="size-6" />
        <span className="px-2 text-center text-[10px]">{t("attachImageFailed")}</span>
      </span>
    );
  }
  if (state === "loading" || !src) {
    return (
      <span className="flex h-24 w-32 items-center justify-center rounded-lg bg-[var(--bg-muted)]">
        <CircleNotch aria-hidden className="size-5 animate-spin text-[var(--text-muted)]" />
      </span>
    );
  }
  return (
    <a
      href={src}
      target="_blank"
      rel="noopener noreferrer"
      className="block overflow-hidden rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]"
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt={attachment.file_name || t("attachImageAlt")}
        className="max-h-56 max-w-[12rem] object-cover"
      />
    </a>
  );
}

/* ---------------------------------- File ---------------------------------- */

function fileIconFor(contentType: string, name: string) {
  if (contentType.includes("pdf") || name.toLowerCase().endsWith(".pdf")) return FilePdf;
  if (contentType.includes("zip") || name.toLowerCase().endsWith(".zip")) return FileZip;
  return FileIcon;
}

function AttachmentFile({
  attachment,
  mine,
}: {
  attachment: MessagingAttachment;
  mine: boolean;
}) {
  const t = useTranslations("messaging");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const Icon = fileIconFor(attachment.content_type, attachment.file_name);

  async function download() {
    if (busy) return;
    setBusy(true);
    setError(false);
    try {
      const blob = await messagingApi.downloadAttachment(attachment.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = attachment.file_name || "attachment";
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Revoke after the click has a chance to start the download.
      window.setTimeout(() => URL.revokeObjectURL(url), 4000);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={download}
      disabled={busy}
      title={t("attachDownload")}
      className={cn(
        "group flex max-w-[16rem] items-center gap-2.5 rounded-lg px-2.5 py-2 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
        mine
          ? "bg-white/15 hover:bg-white/25"
          : "bg-[var(--surface-card)] shadow-[inset_0_0_0_1px_rgba(0,0,0,0.08)] hover:bg-[var(--bg-subtle)]",
      )}
    >
      <span
        className={cn(
          "flex size-9 shrink-0 items-center justify-center rounded-md",
          mine ? "bg-white/20 text-white" : "bg-[var(--bg-muted)] text-[var(--text-secondary)]",
        )}
      >
        {busy ? (
          <CircleNotch aria-hidden className="size-4 animate-spin" />
        ) : (
          <Icon aria-hidden weight="duotone" className="size-5" />
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span
          className={cn(
            "block truncate text-xs font-semibold",
            mine ? "text-white" : "text-[var(--text-primary)]",
          )}
        >
          {attachment.file_name}
        </span>
        <span
          className={cn(
            "block text-[10px]",
            error
              ? "text-[var(--brand-red)]"
              : mine
                ? "text-white/70"
                : "text-[var(--text-muted)]",
          )}
        >
          {error
            ? t("attachDownloadFailed")
            : busy
              ? t("attachDownloading")
              : formatBytes(attachment.size_bytes)}
        </span>
      </span>
      <DownloadSimple
        aria-hidden
        weight="bold"
        className={cn(
          "size-4 shrink-0",
          mine ? "text-white/80" : "text-[var(--text-muted)]",
        )}
      />
    </button>
  );
}
