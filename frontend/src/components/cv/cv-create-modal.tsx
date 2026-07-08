"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle,
  UploadSimple,
  WifiSlash,
} from "@phosphor-icons/react";
import { Button, Input, Modal, useToast } from "@/components/ui";
import {
  ApiError,
  cvApi,
  parseCvQuotaError,
  type CvDetail,
  type CvQuotaInfo,
  type CvTemplate,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { CvDocument, SAMPLE_CV, themeForTemplate } from "@/components/cv/render";
import { cn } from "@/lib/utils";

/** Scale the 794px A4 page into the modal card's 64px-wide thumbnail. */
const CARD_THUMB_SCALE = 64 / 794;

type TranslationFn = {
  (key: string): string;
  has: (key: string) => boolean;
};

function templateLabel(t: TranslationFn, key: string, fallback: string): string {
  return t.has(key) ? t(key) : fallback;
}

export function CvCreateModal({
  open,
  onClose,
  onCreated,
  onOpenUpload,
  onQuotaExceeded,
  initialTemplateId,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (cv: CvDetail) => void;
  onOpenUpload: () => void;
  /** Active-CV limit reached (409). Parent closes this modal and opens recovery. */
  onQuotaExceeded: (info: CvQuotaInfo) => void;
  /** When opened from the template shelf, preselect this template. */
  initialTemplateId?: string | null;
}) {
  const t = useTranslations("cv");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");
  const toast = useToast();
  const apiError = useApiErrorMessage();

  const [title, setTitle] = useState("");
  const [templateId, setTemplateId] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);

  const templates = useQuery({
    queryKey: ["cv", "templates"],
    queryFn: () => cvApi.listTemplates(),
    enabled: open,
    staleTime: 5 * 60_000,
  });

  // When the modal opens from the template shelf, preselect the picked template
  // so the user lands ready to name + create.
  useEffect(() => {
    if (open && initialTemplateId) {
      setTemplateId(initialTemplateId);
    }
  }, [open, initialTemplateId]);

  async function handleCreate() {
    setError(null);
    setOffline(false);

    const trimmed = title.trim();
    if (!trimmed) {
      setError(t("create.errTitle"));
      return;
    }

    setSubmitting(true);
    try {
      const cv = await cvApi.create({
        title: trimmed,
        creation_mode: "blank_template",
        template_id: templateId || null,
        language: "vi",
      });
      toast.show({ tone: "success", title: t("create.createdToast") });
      onCreated(cv);
    } catch (e) {
      const quota = parseCvQuotaError(e);
      if (quota) {
        onClose();
        onQuotaExceeded(quota);
        return;
      }
      // Offline -> friendly retry state instead of a generic failure.
      if (e instanceof ApiError && e.code === "NETWORK_ERROR") {
        setOffline(true);
        return;
      }
      setError(apiError(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t("create.title")}
      description={t("create.subtitle")}
      size="md"
      closeLabel={tc("close")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            {tc("cancel")}
          </Button>
          <Button variant="primary" onClick={handleCreate} loading={submitting}>
            {t("create.submit")}
          </Button>
        </>
      }
    >
      {/* The two supported creation paths: from a template (primary, below) and
          uploading an existing CV (secondary shortcut). */}
      <button
        type="button"
        onClick={() => {
          onClose();
          onOpenUpload();
        }}
        className="flex w-full items-center gap-3 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] p-3 text-left outline-none transition-colors hover:border-[var(--brand-primary)]/50 focus-visible:border-[var(--brand-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/20"
      >
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg icon-chip-success shadow-sm">
          <UploadSimple aria-hidden weight="duotone" className="size-4 text-white" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold text-[var(--text-primary)]">
            {t("create.modeUploadTitle")}
          </span>
          <span className="mt-0.5 block text-xs text-[var(--text-secondary)]">
            {t("create.modeUploadBody")}
          </span>
        </span>
      </button>

      <div className="my-5 flex items-center gap-3" aria-hidden>
        <span className="h-px flex-1 bg-[var(--border-subtle)]" />
        <span className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
          {t("create.orDivider")}
        </span>
        <span className="h-px flex-1 bg-[var(--border-subtle)]" />
      </div>

      <div className="space-y-4">
        <Input
          label={t("create.titleLabel")}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={t("create.titlePlaceholder")}
          required
          error={error ?? undefined}
        />

        <TemplateGallery
          templates={templates.data ?? []}
          selectedId={templateId}
          disabled={templates.isPending}
          onSelect={setTemplateId}
        />

        {offline && (
          <div
            role="alert"
            className="flex items-start gap-3 rounded-xl bg-[var(--amber-100)] p-4"
          >
            <span className="flex size-7 shrink-0 items-center justify-center rounded-lg icon-chip-warning shadow-sm">
              <WifiSlash aria-hidden weight="duotone" className="size-4 text-white" />
            </span>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {tStates("offlineTitle")}
              </p>
              <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
                {tStates("offlineBody")}
              </p>
              <Button
                variant="secondary"
                size="sm"
                className="mt-3"
                loading={submitting}
                onClick={handleCreate}
              >
                {tc("retry")}
              </Button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}

function TemplateGallery({
  templates,
  selectedId,
  disabled,
  onSelect,
}: {
  templates: CvTemplate[];
  selectedId: string;
  disabled?: boolean;
  onSelect: (id: string) => void;
}) {
  const t = useTranslations("cv");
  const selected = selectedId || "";
  return (
    <fieldset>
      <div className="mb-2 flex items-end justify-between gap-3">
        <div>
          <legend className="text-sm font-semibold text-[var(--text-primary)]">
            {t("create.templateGalleryTitle")}
          </legend>
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
            {t("create.templateGalleryHint")}
          </p>
        </div>
      </div>
      <div className="grid gap-2.5 sm:grid-cols-2">
        <TemplateCard
          name={t("create.templateNone")}
          category={t("create.templateCategories.classic")}
          selected={selected === ""}
          disabled={disabled}
          onClick={() => onSelect("")}
        />
        {templates.map((tpl) => (
          <TemplateCard
            key={tpl.id}
            template={tpl}
            name={tpl.name}
            category={templateLabel(
              t,
              `create.templateCategories.${tpl.category}`,
              tpl.category,
            )}
            roles={tpl.layout_schema?.target_roles ?? []}
            strengths={(tpl.layout_schema?.strengths ?? []).map((s) =>
              templateLabel(t, `create.templateStrengths.${s}`, s),
            )}
            selected={selected === tpl.id}
            disabled={disabled}
            onClick={() => onSelect(tpl.id)}
          />
        ))}
      </div>
    </fieldset>
  );
}

function TemplateCard({
  template,
  name,
  category,
  roles = [],
  strengths = [],
  selected,
  disabled,
  onClick,
}: {
  /** Omitted for the "no template" card — falls back to the neutral theme. */
  template?: CvTemplate;
  name: string;
  category: string;
  roles?: string[];
  strengths?: string[];
  selected: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  const t = useTranslations("cv");
  const theme = themeForTemplate(template);
  return (
    <button
      type="button"
      disabled={disabled}
      aria-pressed={selected}
      onClick={onClick}
      className={cn(
        "group flex min-h-[132px] gap-3 rounded-xl border-2 p-3 text-left outline-none transition-colors",
        "focus-visible:border-[var(--brand-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/20",
        disabled
          ? "cursor-not-allowed border-[var(--border-subtle)] opacity-60"
          : selected
            ? "border-[var(--brand-primary)] bg-[var(--surface-secondary)]"
            : "border-[var(--border-default)] bg-[var(--surface-card)] hover:border-[var(--brand-primary)]/45",
      )}
    >
      <span
        aria-hidden
        className="relative block aspect-[210/297] w-16 shrink-0 overflow-hidden rounded-md border border-[var(--border-default)] bg-white"
      >
        {/* Live A4 thumbnail (same renderer as the preview + gallery shelf). */}
        <CvDocument
          content={SAMPLE_CV}
          theme={theme}
          scale={CARD_THUMB_SCALE}
          ariaLabel={t("create.templatePreviewLabel", { name })}
        />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-start justify-between gap-2">
          <span>
            <span className="block text-sm font-bold text-[var(--text-primary)]">
              {name}
            </span>
            <span className="mt-0.5 inline-flex rounded-full bg-[var(--surface-secondary)] px-2 py-0.5 text-[11px] font-semibold text-[var(--text-secondary)]">
              {category}
            </span>
          </span>
          {selected && (
            <CheckCircle
              aria-label={t("create.templateSelected")}
              weight="fill"
              className="size-5 shrink-0 text-[var(--brand-primary)]"
            />
          )}
        </span>
        {roles.length > 0 && (
          <span className="mt-2 block text-xs leading-5 text-[var(--text-secondary)]">
            <strong className="font-semibold text-[var(--text-primary)]">
              {t("create.templateRoleTitle")}:
            </strong>{" "}
            {roles.slice(0, 2).join(", ")}
          </span>
        )}
        {strengths.length > 0 && (
          <span className="mt-1 flex flex-wrap gap-1">
            {strengths.slice(0, 3).map((s) => (
              <span
                key={s}
                className="rounded-md bg-[var(--bg-subtle)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]"
              >
                {s}
              </span>
            ))}
          </span>
        )}
      </span>
    </button>
  );
}
