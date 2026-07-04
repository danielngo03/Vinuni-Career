"use client";

import { useCallback, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Circle, Square, Trash, UploadSimple } from "@phosphor-icons/react";
import { Button, Modal, useToast } from "@/components/ui";
import type { CvCanvasPhoto } from "@/lib/api";
import { cn } from "@/lib/utils";

export type PhotoShape = "circle" | "square" | "rounded";

const MAX_BYTES = 8 * 1024 * 1024;
const ACCEPTED_TYPES = ["image/png", "image/jpeg", "image/webp"];

/**
 * Photo replace/crop modal (`docs/CV_STUDIO_SPEC.md`): file picker, a
 * draggable/resizable square crop rectangle over the source image, and a
 * shape picker. Emits normalized 0..1 crop fractions on save, matching
 * `PATCH /cvs/{id}/photo`'s `crop_x/y/width/height` contract.
 */
export function CvPhotoEditor({
  open,
  onClose,
  currentPhoto,
  saving,
  onSave,
  onRemove,
}: {
  open: boolean;
  onClose: () => void;
  currentPhoto: CvCanvasPhoto | null | undefined;
  saving: boolean;
  onSave: (params: {
    file: File;
    crop: { x: number; y: number; width: number; height: number };
    shape: PhotoShape;
  }) => void;
  onRemove: () => void;
}) {
  const t = useTranslations("cv");
  const toast = useToast();

  const [file, setFile] = useState<File | null>(null);
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [shape, setShape] = useState<PhotoShape>(currentPhoto?.shape ?? "circle");
  const [crop, setCrop] = useState({ x: 0.1, y: 0.1, width: 0.8, height: 0.8 });
  const [dragging, setDragging] = useState(false);
  const frameRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function pickFile(f: File) {
    if (!ACCEPTED_TYPES.includes(f.type)) {
      toast.show({ tone: "error", title: t("canvas.photoErrType") });
      return;
    }
    if (f.size > MAX_BYTES) {
      toast.show({ tone: "error", title: t("canvas.photoErrSize") });
      return;
    }
    setFile(f);
    setCrop({ x: 0.1, y: 0.1, width: 0.8, height: 0.8 });
    setObjectUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(f);
    });
  }

  const handleDragMove = useCallback(
    (e: React.MouseEvent) => {
      if (!dragging || !frameRef.current) return;
      const rect = frameRef.current.getBoundingClientRect();
      const cx = Math.min(Math.max((e.clientX - rect.left) / rect.width, 0), 1);
      const cy = Math.min(Math.max((e.clientY - rect.top) / rect.height, 0), 1);
      setCrop((prev) => {
        const size = prev.width;
        const half = size / 2;
        return {
          ...prev,
          x: Math.min(Math.max(cx - half, 0), 1 - size),
          y: Math.min(Math.max(cy - half, 0), 1 - size),
        };
      });
    },
    [dragging],
  );

  function handleSave() {
    if (!file) return;
    onSave({ file, crop, shape });
  }

  function handleClose() {
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    setFile(null);
    setObjectUrl(null);
    onClose();
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title={t("canvas.photoEditorTitle")}
      description={t("canvas.photoEditorBody")}
      size="sm"
      closeLabel={t("canvas.close")}
      footer={
        <>
          {currentPhoto?.url && (
            <Button variant="ghost" onClick={onRemove} disabled={saving}>
              <Trash aria-hidden weight="bold" className="size-4" />
              {t("canvas.removePhoto")}
            </Button>
          )}
          <Button variant="secondary" onClick={handleClose} disabled={saving}>
            {t("canvas.cancel")}
          </Button>
          <Button variant="primary" onClick={handleSave} disabled={!file || saving} loading={saving}>
            {t("canvas.savePhoto")}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_TYPES.join(",")}
          className="sr-only"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) pickFile(f);
          }}
        />

        {!objectUrl ? (
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="flex w-full flex-col items-center gap-2 rounded-xl border-2 border-dashed border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] px-4 py-10 text-center outline-none transition hover:border-[var(--brand-primary)]/50 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
          >
            <UploadSimple aria-hidden weight="duotone" className="size-6 text-[var(--text-muted)]" />
            <span className="text-sm font-medium text-[var(--text-primary)]">
              {t("canvas.choosePhoto")}
            </span>
            <span className="text-xs text-[var(--text-muted)]">{t("canvas.photoHint")}</span>
          </button>
        ) : (
          <div>
            <div
              ref={frameRef}
              className="relative mx-auto aspect-square w-full max-w-xs select-none overflow-hidden rounded-lg bg-black/5"
              onMouseDown={() => setDragging(true)}
              onMouseUp={() => setDragging(false)}
              onMouseLeave={() => setDragging(false)}
              onMouseMove={handleDragMove}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={objectUrl} alt="" className="absolute inset-0 size-full object-contain" draggable={false} />
              <div
                aria-hidden
                className={cn(
                  "absolute cursor-move border-2 border-white shadow-[0_0_0_9999px_rgba(0,0,0,0.45)]",
                  shape === "circle" && "rounded-full",
                  shape === "rounded" && "rounded-xl",
                )}
                style={{
                  left: `${crop.x * 100}%`,
                  top: `${crop.y * 100}%`,
                  width: `${crop.width * 100}%`,
                  height: `${crop.height * 100}%`,
                }}
              />
            </div>
            <p className="mt-2 text-center text-xs text-[var(--text-muted)]">
              {t("canvas.dragToCrop")}
            </p>
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-lg border border-[var(--glass-border-strong)] px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] outline-none hover:bg-[var(--glass-surface-light)]"
            >
              <UploadSimple aria-hidden weight="bold" className="size-3.5" />
              {t("canvas.chooseDifferentPhoto")}
            </button>
          </div>
        )}

        <div>
          <p className="mb-1.5 text-xs font-semibold text-[var(--text-secondary)]">
            {t("canvas.photoShape")}
          </p>
          <div className="flex gap-1.5">
            {(
              [
                { value: "circle" as const, Icon: Circle, label: t("canvas.shapeCircle") },
                { value: "square" as const, Icon: Square, label: t("canvas.shapeSquare") },
                { value: "rounded" as const, Icon: Square, label: t("canvas.shapeRounded") },
              ]
            ).map(({ value, Icon, label }) => (
              <button
                key={value}
                type="button"
                aria-pressed={shape === value}
                onClick={() => setShape(value)}
                className={cn(
                  "flex flex-1 items-center justify-center gap-1.5 rounded-lg border px-2 py-1.5 text-xs font-semibold outline-none transition-colors",
                  shape === value
                    ? "border-[var(--brand-primary)]/60 bg-[var(--brand-primary)]/10 text-[var(--brand-primary)]"
                    : "border-[var(--glass-border-strong)] text-[var(--text-secondary)] hover:bg-[var(--glass-surface-light)]",
                )}
              >
                <Icon aria-hidden weight="bold" className={cn("size-3.5", value === "rounded" && "rounded-sm")} />
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </Modal>
  );
}
