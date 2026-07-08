"use client";

import { useTranslations } from "next-intl";
import { FileArrowUp, FilePlus, WarningCircle } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

const ACCEPT = ".pdf,.doc,.docx,.txt,.png,.jpg,.jpeg,.webp";

export function PickStep({
  dragOver,
  onDragState,
  onDrop,
  onFile,
  clientError,
  onCreateFromTemplate,
}: {
  dragOver: boolean;
  onDragState: (v: boolean) => void;
  onDrop: (e: React.DragEvent) => void;
  onFile: (f: File) => void;
  clientError: string | null;
  onCreateFromTemplate: () => void;
}) {
  const t = useTranslations("cv.import");
  return (
    <div className="mx-auto max-w-2xl">
      <label
        htmlFor="cv-import-file"
        onDragOver={(e) => {
          e.preventDefault();
          onDragState(true);
        }}
        onDragLeave={() => onDragState(false)}
        onDrop={onDrop}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-6 py-14 text-center transition-colors focus-within:border-[var(--brand-primary)]",
          dragOver
            ? "border-[var(--brand-primary)] bg-[var(--blue-50)]"
            : "border-[var(--border-default)] bg-[var(--glass-surface)] hover:border-[var(--brand-primary)] hover:bg-[var(--glass-surface-heavy)]",
        )}
      >
        <span className="flex size-14 items-center justify-center rounded-2xl icon-chip-primary shadow-[0_4px_16px_rgba(45,95,166,0.35)]">
          <FileArrowUp aria-hidden weight="duotone" className="size-7 text-white" />
        </span>
        <span className="text-base font-semibold text-[var(--text-primary)]">
          {t("dropTitle")}
        </span>
        <span className="max-w-sm text-xs text-[var(--text-secondary)]">
          {t("dropHint")}
        </span>
        <input
          id="cv-import-file"
          type="file"
          accept={ACCEPT}
          className="sr-only"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onFile(f);
            e.target.value = "";
          }}
        />
      </label>
      {clientError && (
        <p
          role="alert"
          className="mt-3 flex items-center gap-2 text-sm font-medium text-[var(--brand-red)]"
        >
          <WarningCircle aria-hidden weight="fill" className="size-4" />
          {clientError}
        </p>
      )}
      <div className="mt-4 flex items-center justify-center gap-2 text-sm text-[var(--text-secondary)]">
        <span>{t("orDivider")}</span>
        <button
          type="button"
          onClick={onCreateFromTemplate}
          className="inline-flex items-center gap-1.5 font-semibold text-[var(--brand-primary)] outline-none hover:underline focus-visible:underline"
        >
          <FilePlus aria-hidden weight="bold" className="size-4" />
          {t("startFromTemplate")}
        </button>
      </div>
    </div>
  );
}
