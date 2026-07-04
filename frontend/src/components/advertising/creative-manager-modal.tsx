"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  UploadSimple,
  Trash,
  ArrowClockwise,
  WarningCircle,
  ImageSquare,
  Crosshair,
} from "@phosphor-icons/react";
import {
  Button,
  Input,
  Modal,
  Select,
  StatusBadge,
  useToast,
  DisclosureLabel,
} from "@/components/ui";
import {
  ApiError,
  advertisingApi,
  CREATIVE_SLOTS,
  PRIMARY_CREATIVE_SLOTS,
  CREATIVE_SLOT_SPECS,
  type CreativeSlot,
  type Placement,
  type PlacementCreative,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { cn } from "@/lib/utils";
import {
  CreativeImage,
  SlotPreviewFrames,
  creativeStatusTone,
} from "./creative-preview";

/** Client-side guard mirrors the server contract (≤5MB, PNG/JPEG/WebP). */
const MAX_BYTES = 5 * 1024 * 1024;
const ACCEPT = "image/png,image/jpeg,image/webp";
const ALLOWED_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);

interface DraftState {
  slot: CreativeSlot;
  file: File | null;
  altVi: string;
  altEn: string;
  clickTarget: string;
  focal: { x: number; y: number };
}

const EMPTY_DRAFT: DraftState = {
  slot: "homepage_hero",
  file: null,
  altVi: "",
  altEn: "",
  clickTarget: "",
  focal: { x: 0.5, y: 0.5 },
};

/**
 * Partner creative manager (spec §5/§6 steps 2–4): per-slot banner upload with a
 * client pre-check + size/aspect hint, alt vi/en, a focal-point picker, a click
 * target, an exact desktop/mobile placement preview, the moderation status of each
 * creative, and the "asset required before this can run" state. Replace = delete +
 * re-upload (a new creative always re-enters review). 422 surfaces inline; 409 via
 * toast. The `placement` prop is re-derived from the live query upstream so the
 * list stays fresh after a mutation.
 */
export function CreativeManagerModal({
  open,
  onClose,
  placement,
}: {
  open: boolean;
  onClose: () => void;
  placement: Placement | null;
}) {
  const t = useTranslations("advertisingCreatives");
  const tc = useTranslations("common");
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const inputRef = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState<DraftState>(EMPTY_DRAFT);
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PlacementCreative | null>(null);

  const creatives = placement?.creatives ?? [];
  const missing = (placement?.missing_primary_slots ?? []) as CreativeSlot[];

  /* Object-URL lifecycle for the staged local preview. */
  useEffect(() => {
    if (!draft.file) {
      setObjectUrl(null);
      return;
    }
    const url = URL.createObjectURL(draft.file);
    setObjectUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [draft.file]);

  /* Reset the whole form whenever the modal (re)opens. */
  useEffect(() => {
    if (!open) return;
    setDraft(EMPTY_DRAFT);
    setFieldError(null);
    setDeleteTarget(null);
    if (inputRef.current) inputRef.current.value = "";
  }, [open]);

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["advertising", "placements"] });
  }

  function clearFile() {
    setDraft((d) => ({ ...d, file: null, focal: { x: 0.5, y: 0.5 } }));
    if (inputRef.current) inputRef.current.value = "";
  }

  function onSelectFile(file: File | null | undefined) {
    setFieldError(null);
    if (!file) return;
    if (!ALLOWED_TYPES.has(file.type)) {
      setFieldError(t("err.unsupportedType"));
      return;
    }
    if (file.size === 0) {
      setFieldError(t("err.emptyFile"));
      return;
    }
    if (file.size > MAX_BYTES) {
      setFieldError(t("err.tooLarge"));
      return;
    }
    setDraft((d) => ({ ...d, file, focal: { x: 0.5, y: 0.5 } }));
  }

  function mapUploadError(e: unknown): string {
    if (e instanceof ApiError) {
      const reason =
        typeof e.details?.reason === "string" ? e.details.reason : undefined;
      const field =
        typeof e.details?.field === "string" ? e.details.field : undefined;
      if (e.isValidation) {
        if (reason === "file_too_large") return t("err.tooLarge");
        if (reason === "unsupported_image_type") return t("err.unsupportedType");
        if (reason === "empty_file") return t("err.emptyFile");
        if (field === "slot") return t("err.slot");
        if (field === "focal_x" || field === "focal_y") return t("err.focal");
        return e.message || t("err.generic");
      }
      if (e.code === "NETWORK_ERROR") return t("err.network");
    }
    return getMessage(e);
  }

  const upload = useMutation({
    mutationFn: () => {
      if (!placement || !draft.file) throw new Error("no_file");
      return advertisingApi.uploadCreative(placement.id, {
        file: draft.file,
        slot: draft.slot,
        alt_vi: draft.altVi.trim() || undefined,
        alt_en: draft.altEn.trim() || undefined,
        focal_x: round2(draft.focal.x),
        focal_y: round2(draft.focal.y),
        click_target: draft.clickTarget.trim() || undefined,
      });
    },
    onSuccess: () => {
      setDraft((d) => ({ ...EMPTY_DRAFT, slot: d.slot }));
      if (inputRef.current) inputRef.current.value = "";
      setFieldError(null);
      toast.show({ tone: "success", title: t("uploadedToast") });
      refresh();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.isConflict) {
        toast.show({ tone: "error", title: t("err.conflict") });
        refresh();
        return;
      }
      setFieldError(mapUploadError(e));
    },
  });

  const remove = useMutation({
    mutationFn: (c: PlacementCreative) => advertisingApi.deleteCreative(c.id),
    onSuccess: () => {
      setDeleteTarget(null);
      toast.show({ tone: "success", title: t("deletedToast") });
      refresh();
    },
    onError: (e) => {
      setDeleteTarget(null);
      toast.show({ tone: "error", title: getMessage(e) });
    },
  });

  const slotSpec = CREATIVE_SLOT_SPECS[draft.slot];
  const isNetworkError = fieldError === t("err.network");

  return (
    <>
      <Modal
        open={open && placement !== null}
        onClose={onClose}
        title={t("manageTitle")}
        description={placement?.target_title ?? undefined}
        size="lg"
        closeLabel={tc("close")}
        footer={
          <Button variant="ghost" onClick={onClose}>
            {tc("close")}
          </Button>
        }
      >
        {placement && (
          <div className="space-y-6">
            {/* Disclosure class of this inventory. */}
            <div className="flex flex-wrap items-center gap-2 text-sm text-[var(--text-secondary)]">
              <span className="font-semibold text-[var(--text-primary)]">
                {t("disclosureClassLabel")}
              </span>
              {placement.disclosure ? (
                <DisclosureLabel disclosure={placement.disclosure} />
              ) : (
                <span>—</span>
              )}
            </div>

            {/* Missing primary-asset state. */}
            {missing.length > 0 && (
              <div className="flex items-start gap-2.5 rounded-xl border border-[var(--amber-600)]/40 bg-[var(--amber-100)] px-3.5 py-3">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-md icon-chip-warning shadow-sm">
                  <WarningCircle aria-hidden weight="duotone" className="size-3.5 text-white" />
                </span>
                <div>
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    {t("missingAssetsTitle")}
                  </p>
                  <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                    {t("missingAssetsBody", {
                      slots: missing.map((s) => t(`slots.${s}`)).join(", "),
                    })}
                  </p>
                </div>
              </div>
            )}

            {/* Existing creatives. */}
            <section className="space-y-3">
              <h3 className="flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-md icon-chip-success shadow-sm">
                  <ImageSquare aria-hidden weight="duotone" className="size-3.5 text-white" />
                </span>
                {t("existingTitle")}
              </h3>
              {creatives.length === 0 ? (
                <p className="rounded-xl border border-[var(--border-default)] bg-white px-3.5 py-3 text-sm text-[var(--text-secondary)] ">
                  {t("noCreatives")}
                </p>
              ) : (
                <ul className="space-y-3">
                  {creatives.map((c) => (
                    <li
                      key={c.id}
                      className="flex gap-3 rounded-xl border border-[var(--border-default)] bg-white p-3"
                    >
                      <div className="h-20 w-28 shrink-0 overflow-hidden rounded-lg border border-[var(--border-default)]">
                        <CreativeImage
                          src={c.image_url}
                          alt={c.alt}
                          focal={c.focal_point}
                          unavailableLabel={t("previewStaged")}
                        />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-semibold text-[var(--text-primary)]">
                            {c.slot_label}
                          </span>
                          {PRIMARY_CREATIVE_SLOTS.includes(
                            c.slot as CreativeSlot,
                          ) && (
                            <span className="rounded bg-[var(--bg-subtle)] px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-[var(--text-muted)]">
                              {t("primaryBadge")}
                            </span>
                          )}
                          <StatusBadge tone={creativeStatusTone(c.moderation_status)}>
                            {c.moderation_status_label}
                          </StatusBadge>
                        </div>
                        <p className="mt-1 truncate text-xs text-[var(--text-secondary)]">
                          {c.alt ?? t("noAlt")}
                        </p>
                        {c.moderation_status === "rejected" &&
                          c.moderation_note && (
                            <p className="mt-1 text-xs text-[var(--brand-red)]">
                              {t("rejectedNote", { note: c.moderation_note })}
                            </p>
                          )}
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setDeleteTarget(c)}
                      >
                        <Trash aria-hidden weight="bold" className="size-4" />
                        {tc("delete")}
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {/* Upload a new creative. */}
            <section className="space-y-3 border-t border-[var(--border-default)] pt-5">
              <h3 className="flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-md icon-chip-success shadow-sm">
                  <UploadSimple aria-hidden weight="bold" className="size-3.5 text-white" />
                </span>
                {t("addTitle")}
              </h3>

              <Select
                label={t("slotLabel")}
                value={draft.slot}
                onChange={(e) =>
                  setDraft((d) => ({
                    ...d,
                    slot: e.target.value as CreativeSlot,
                  }))
                }
                options={CREATIVE_SLOTS.map((s) => ({
                  value: s,
                  label: PRIMARY_CREATIVE_SLOTS.includes(s)
                    ? `${t(`slots.${s}`)} · ${t("primaryBadge")}`
                    : t(`slots.${s}`),
                }))}
                help={
                  slotSpec
                    ? t("slotHint", {
                        desktop: slotSpec.desktop ?? "—",
                        mobile: slotSpec.mobile ?? "—",
                      })
                    : undefined
                }
              />

              {!draft.file ? (
                <DropZone
                  inputRef={inputRef}
                  accept={ACCEPT}
                  label={t("fileLabel")}
                  dropHint={t("dropHint")}
                  fileHint={t("fileHint")}
                  onFile={onSelectFile}
                />
              ) : (
                <div className="space-y-4">
                  <FocalPointPicker
                    src={objectUrl}
                    alt={draft.altEn || draft.altVi || null}
                    focal={draft.focal}
                    onChange={(focal) => setDraft((d) => ({ ...d, focal }))}
                    title={t("focalTitle")}
                    help={t("focalHelp")}
                    ariaLabel={t("focalAria")}
                    xLabel={t("focalX")}
                    yLabel={t("focalY")}
                  />

                  <Input
                    id="creative-alt-vi"
                    label={t("altViLabel")}
                    value={draft.altVi}
                    maxLength={160}
                    onChange={(e) =>
                      setDraft((d) => ({ ...d, altVi: e.target.value }))
                    }
                    help={t("altHint")}
                  />
                  <Input
                    id="creative-alt-en"
                    label={t("altEnLabel")}
                    value={draft.altEn}
                    maxLength={160}
                    onChange={(e) =>
                      setDraft((d) => ({ ...d, altEn: e.target.value }))
                    }
                  />
                  <Input
                    id="creative-click-target"
                    type="url"
                    label={t("clickTargetLabel")}
                    value={draft.clickTarget}
                    placeholder={t("clickTargetPlaceholder")}
                    onChange={(e) =>
                      setDraft((d) => ({ ...d, clickTarget: e.target.value }))
                    }
                    help={t("clickTargetHint")}
                  />

                  {/* Exact desktop/mobile placement preview. */}
                  <div className="rounded-xl border border-[var(--border-default)] bg-white p-3 ">
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                      {t("placementPreviewTitle")}
                    </p>
                    <SlotPreviewFrames
                      slot={draft.slot}
                      src={null}
                      localSrc={objectUrl}
                      alt={draft.altEn || draft.altVi || null}
                      focal={draft.focal}
                      desktopLabel={t("previewDesktop")}
                      mobileLabel={t("previewMobile")}
                      unavailableLabel={t("previewUnavailable")}
                    />
                  </div>

                  {fieldError && (
                    <p
                      role="alert"
                      className="flex flex-wrap items-center gap-2 rounded-xl border border-[var(--red-400)]/40 bg-[var(--red-50)] px-3 py-2 text-sm font-medium text-[var(--brand-red)]"
                    >
                      <span>{fieldError}</span>
                      {isNetworkError && (
                        <button
                          type="button"
                          onClick={() => upload.mutate()}
                          className="inline-flex items-center gap-1 font-semibold text-[var(--brand-primary)] underline underline-offset-2"
                        >
                          <ArrowClockwise
                            aria-hidden
                            weight="bold"
                            className="size-3.5"
                          />
                          {t("err.retry")}
                        </button>
                      )}
                    </p>
                  )}

                  <div className="flex flex-wrap items-center gap-3">
                    <Button
                      variant="primary"
                      loading={upload.isPending}
                      onClick={() => upload.mutate()}
                    >
                      <UploadSimple aria-hidden weight="bold" className="size-4" />
                      {t("uploadBtn")}
                    </Button>
                    <Button
                      variant="ghost"
                      disabled={upload.isPending}
                      onClick={() => {
                        clearFile();
                        setFieldError(null);
                      }}
                    >
                      {t("cancelFile")}
                    </Button>
                  </div>
                </div>
              )}

              {!draft.file && fieldError && (
                <p
                  role="alert"
                  className="rounded-xl border border-[var(--red-400)]/40 bg-[var(--red-50)] px-3 py-2 text-sm font-medium text-[var(--brand-red)]"
                >
                  {fieldError}
                </p>
              )}
            </section>
          </div>
        )}
      </Modal>

      {/* Delete creative confirmation. */}
      <Modal
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        title={t("deleteTitle")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>
              {tc("back")}
            </Button>
            <Button
              variant="danger"
              loading={remove.isPending}
              onClick={() => deleteTarget && remove.mutate(deleteTarget)}
            >
              {tc("delete")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">{t("deleteBody")}</p>
      </Modal>
    </>
  );
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

/* --------------------------------- Drop zone -------------------------------- */

function DropZone({
  inputRef,
  accept,
  label,
  dropHint,
  fileHint,
  onFile,
}: {
  inputRef: React.RefObject<HTMLInputElement | null>;
  accept: string;
  label: string;
  dropHint: string;
  fileHint: string;
  onFile: (file: File | null | undefined) => void;
}) {
  const [dragging, setDragging] = useState(false);

  return (
    <div>
      <label
        htmlFor="creative-file"
        className="mb-1.5 block text-sm font-semibold text-[var(--text-primary)]"
      >
        {label}
      </label>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          onFile(e.dataTransfer.files?.[0]);
        }}
        className={cn(
          "flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-6 text-center transition-colors",
          dragging
            ? "border-[var(--brand-primary)] bg-[var(--blue-50)]"
            : "border-[var(--border-default)] bg-[var(--bg-subtle)]",
        )}
      >
        <ImageSquare
          aria-hidden
          weight="duotone"
          className="size-8 text-[var(--text-muted)]"
        />
        <p className="text-sm text-[var(--text-secondary)]">{dropHint}</p>
        <input
          ref={inputRef}
          id="creative-file"
          type="file"
          accept={accept}
          aria-describedby="creative-file-hint"
          onChange={(e) => onFile(e.target.files?.[0])}
          className="block w-full max-w-xs cursor-pointer text-sm text-[var(--text-secondary)] file:mr-4 file:cursor-pointer file:rounded-lg file:border-0 file:bg-white file:px-4 file:py-2 file:text-sm file:font-semibold file:text-[var(--brand-primary)] hover:file:bg-[var(--blue-50)]"
        />
        <p id="creative-file-hint" className="text-xs text-[var(--text-muted)]">
          {fileHint}
        </p>
      </div>
    </div>
  );
}

/* ------------------------------ Focal-point picker -------------------------- */

const STEP = 0.02;

/**
 * Focal-point picker: click anywhere on the image to set the responsive crop
 * focus, or use the keyboard (arrow keys nudge by 2%) — the region is focusable
 * with a live aria description. Two labeled numeric inputs provide an explicit
 * keyboard path as well (spec a11y requirement).
 */
function FocalPointPicker({
  src,
  alt,
  focal,
  onChange,
  title,
  help,
  ariaLabel,
  xLabel,
  yLabel,
}: {
  src: string | null;
  alt: string | null;
  focal: { x: number; y: number };
  onChange: (focal: { x: number; y: number }) => void;
  title: string;
  help: string;
  ariaLabel: string;
  xLabel: string;
  yLabel: string;
}) {
  const boxRef = useRef<HTMLDivElement>(null);

  const setFromPointer = useCallback(
    (clientX: number, clientY: number) => {
      const box = boxRef.current;
      if (!box) return;
      const rect = box.getBoundingClientRect();
      const x = clamp01((clientX - rect.left) / rect.width);
      const y = clamp01((clientY - rect.top) / rect.height);
      onChange({ x: round2(x), y: round2(y) });
    },
    [onChange],
  );

  function onKeyDown(e: React.KeyboardEvent) {
    let { x, y } = focal;
    switch (e.key) {
      case "ArrowLeft":
        x -= STEP;
        break;
      case "ArrowRight":
        x += STEP;
        break;
      case "ArrowUp":
        y -= STEP;
        break;
      case "ArrowDown":
        y += STEP;
        break;
      default:
        return;
    }
    e.preventDefault();
    onChange({ x: round2(clamp01(x)), y: round2(clamp01(y)) });
  }

  const pctX = Math.round(clamp01(focal.x) * 100);
  const pctY = Math.round(clamp01(focal.y) * 100);

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1.5">
        <Crosshair
          aria-hidden
          weight="duotone"
          className="size-4 text-[var(--brand-primary)]"
        />
        <span className="text-sm font-semibold text-[var(--text-primary)]">
          {title}
        </span>
      </div>
      <div
        ref={boxRef}
        role="application"
        aria-label={`${ariaLabel} — X ${pctX}%, Y ${pctY}%`}
        tabIndex={0}
        onKeyDown={onKeyDown}
        onClick={(e) => setFromPointer(e.clientX, e.clientY)}
        className="relative h-44 w-full cursor-crosshair overflow-hidden rounded-lg border border-[var(--border-default)] bg-[var(--bg-subtle)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
      >
        {src && (
          // eslint-disable-next-line @next/next/no-img-element -- local blob preview.
          <img
            src={src}
            alt={alt ?? ""}
            className="pointer-events-none h-full w-full object-contain"
          />
        )}
        {/* Focal marker. */}
        <span
          aria-hidden
          className="pointer-events-none absolute -ml-3 -mt-3 size-6 rounded-full border-2 border-white bg-[var(--brand-primary)]/30 shadow-[0_0_0_1px_var(--brand-primary)]"
          style={{ left: `${pctX}%`, top: `${pctY}%` }}
        />
      </div>
      <p className="text-xs text-[var(--text-muted)]">{help}</p>
      <div className="grid grid-cols-2 gap-3">
        <Input
          id="focal-x"
          type="number"
          min={0}
          max={100}
          label={xLabel}
          value={String(pctX)}
          onChange={(e) =>
            onChange({
              x: round2(clamp01(Number(e.target.value) / 100)),
              y: focal.y,
            })
          }
        />
        <Input
          id="focal-y"
          type="number"
          min={0}
          max={100}
          label={yLabel}
          value={String(pctY)}
          onChange={(e) =>
            onChange({
              x: focal.x,
              y: round2(clamp01(Number(e.target.value) / 100)),
            })
          }
        />
      </div>
    </div>
  );
}

function clamp01(n: number): number {
  if (Number.isNaN(n)) return 0.5;
  return Math.min(1, Math.max(0, n));
}
