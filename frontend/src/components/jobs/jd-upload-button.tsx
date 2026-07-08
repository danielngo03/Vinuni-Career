"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { FilePdf, ArrowsClockwise } from "@phosphor-icons/react";
import { useToast } from "@/components/ui";
import { jobsApi, ApiError, type JdUploadResult } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  onExtracted: (result: JdUploadResult) => void;
  disabled?: boolean;
  label?: string;
  showFileName?: boolean;
  className?: string;
}

const ACCEPT = ".pdf,.docx,.txt,.png,.jpg,.jpeg,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,image/png,image/jpeg";

const JD_REJECT_REASONS = new Set(["not_a_jd", "blank", "low_quality_scan", "insufficient"]);

export function JdUploadButton({
  onExtracted,
  disabled,
  label,
  showFileName = true,
  className,
}: Props) {
  const t = useTranslations("jobs");
  const tf = useTranslations("jobs.form");
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (file: File) => jobsApi.uploadJd(file),
    onSuccess: (result) => {
      // Show fallback toast here (AI unavailable path); the success/filled toast
      // is shown inside handleJdExtracted so it fires after fields are populated.
      if (!result.is_ai_extraction) {
        toast.show({ tone: "info", title: t("jdUploadFallback") });
      }
      onExtracted(result);
    },
    onError: (error) => {
      if (error instanceof ApiError) {
        const reason =
          typeof error.details?.reason === "string" ? error.details.reason : undefined;
        if (reason && JD_REJECT_REASONS.has(reason)) {
          const keyMap: Record<string, string> = {
            not_a_jd: "uploadJdRejected.notAJd",
            blank: "uploadJdRejected.blank",
            low_quality_scan: "uploadJdRejected.lowQuality",
            insufficient: "uploadJdRejected.insufficient",
          };
          const key = keyMap[reason] ?? "uploadJdError";
          toast.show({ tone: "error", title: tf(key as Parameters<typeof tf>[0]) });
          setFileName(null);
          return;
        }
      }
      toast.show({ tone: "error", title: t("jdUploadError") });
      setFileName(null);
    },
  });

  function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    mutation.mutate(file);
    // Reset so the same file can be re-uploaded if needed.
    e.target.value = "";
  }

  return (
    <div className="flex items-center gap-2">
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        onChange={handleFile}
        className="sr-only"
        aria-label={tf("uploadJdLabel")}
      />
      <button
        type="button"
        disabled={disabled || mutation.isPending}
        onClick={() => inputRef.current?.click()}
        className={cn(
          "inline-flex items-center gap-2 rounded-full border border-[var(--border-default)] bg-[var(--surface-card)] px-4 py-2.5 text-sm font-semibold text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-subtle)] disabled:opacity-50",
          className,
        )}
      >
        {mutation.isPending ? (
          <ArrowsClockwise aria-hidden weight="bold" className="size-4 animate-spin" />
        ) : (
          <FilePdf aria-hidden weight="duotone" className="size-4" />
        )}
        {mutation.isPending ? tf("uploadJdExtracting") : (label ?? tf("uploadJdCta"))}
      </button>
      {showFileName && fileName && !mutation.isPending && (
        <span className="max-w-[160px] truncate text-xs text-[var(--text-muted)]">
          {fileName}
        </span>
      )}
    </div>
  );
}
