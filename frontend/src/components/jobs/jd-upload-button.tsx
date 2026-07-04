"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { FilePdf, ArrowsClockwise } from "@phosphor-icons/react";
import { useToast } from "@/components/ui";
import { jobsApi, type JdUploadResult } from "@/lib/api";

interface Props {
  onExtracted: (result: JdUploadResult) => void;
  disabled?: boolean;
}

const ACCEPT = ".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain";

export function JdUploadButton({ onExtracted, disabled }: Props) {
  const t = useTranslations("jobs");
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (file: File) => jobsApi.uploadJd(file),
    onSuccess: (result) => {
      onExtracted(result);
      if (result.is_ai_extraction) {
        toast.show({ tone: "success", title: t("jdUploadSuccess") });
      } else {
        toast.show({ tone: "info", title: t("jdUploadFallback") });
      }
    },
    onError: () => {
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
        aria-label={t("jdUploadLabel")}
      />
      <button
        type="button"
        disabled={disabled || mutation.isPending}
        onClick={() => inputRef.current?.click()}
        className="flex items-center gap-1.5 rounded-xl border border-teal-500/30 bg-white px-3 py-2 text-sm font-semibold text-teal-700 shadow-sm transition-colors hover:bg-teal-50/60 disabled:opacity-50"
      >
        {mutation.isPending ? (
          <ArrowsClockwise aria-hidden weight="bold" className="size-4 animate-spin" />
        ) : (
          <FilePdf aria-hidden weight="duotone" className="size-4" />
        )}
        {mutation.isPending ? t("jdUploadExtracting") : t("jdUploadCta")}
      </button>
      {fileName && !mutation.isPending && (
        <span className="max-w-[160px] truncate text-xs text-[var(--text-muted)]">
          {fileName}
        </span>
      )}
    </div>
  );
}
