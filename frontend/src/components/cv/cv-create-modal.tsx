"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  FileDashed,
  NotePencil,
  Sparkle,
  UploadSimple,
  UserCircle,
  WifiSlash,
  Crown,
  CheckCircle,
} from "@phosphor-icons/react";
import {
  Button,
  Input,
  Modal,
  Textarea,
  useToast,
} from "@/components/ui";
import {
  ApiError,
  cvApi,
  isCvSourceRequiredError,
  parseCvQuotaError,
  type CvCreationMode,
  type CvDetail,
  type CvQuotaInfo,
  type CvSourceInput,
  type CvTemplate,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { cn } from "@/lib/utils";

type Choosable = "blank_template" | "profile_import" | "notes_import" | "ai_assisted_draft";

const NOTES_MAX = 5000;

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
  /** When opened from the template shelf, preselect this template + blank mode. */
  initialTemplateId?: string | null;
}) {
  const t = useTranslations("cv");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");
  const toast = useToast();
  const apiError = useApiErrorMessage();

  const [mode, setMode] = useState<Choosable>("blank_template");
  const [title, setTitle] = useState("");
  const [templateId, setTemplateId] = useState<string>("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notesError, setNotesError] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);

  const templates = useQuery({
    queryKey: ["cv", "templates"],
    queryFn: () => cvApi.listTemplates(),
    enabled: open,
    staleTime: 5 * 60_000,
  });

  // When the modal opens from the template shelf, preselect the picked template
  // and the blank-from-template flow so the user lands ready to name + create.
  useEffect(() => {
    if (open && initialTemplateId) {
      setMode("blank_template");
      setTemplateId(initialTemplateId);
    }
  }, [open, initialTemplateId]);

  const notesEmpty = notes.trim().length === 0;
  const submitDisabled = mode === "notes_import" && notesEmpty;

  function selectMode(next: Choosable) {
    setMode(next);
    setError(null);
    setNotesError(null);
    setOffline(false);
  }

  async function handleCreate() {
    setError(null);
    setNotesError(null);
    setOffline(false);

    const trimmed = title.trim();
    if (!trimmed) {
      setError(t("create.errTitle"));
      return;
    }
    if (mode === "notes_import" && notesEmpty) {
      setNotesError(t("create.errNotesRequired"));
      return;
    }

    let source: CvSourceInput | null = null;
    if (mode === "profile_import") source = { import_profile: true };
    else if (mode === "notes_import") source = { raw_notes: notes.trim() };
    else if (mode === "ai_assisted_draft" && notes.trim()) source = { raw_notes: notes.trim() };

    setSubmitting(true);
    try {
      const cv = await cvApi.create({
        title: trimmed,
        creation_mode: mode as CvCreationMode,
        template_id: templateId || null,
        language: "vi",
        source,
      });
      toast.show({ tone: "success", title: t("create.createdToast") });
      // notes_import seeds sections server-side and makes no AI call — route
      // straight into the builder, no diff-review step for this path.
      onCreated(cv);
    } catch (e) {
      const quota = parseCvQuotaError(e);
      if (quota) {
        onClose();
        onQuotaExceeded(quota);
        return;
      }
      // Empty/whitespace notes rejected server-side -> inline field error.
      if (isCvSourceRequiredError(e, "raw_notes")) {
        setNotesError(t("create.errNotesRequired"));
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

  const modeCards: {
    value: Choosable | "upload" | "ai";
    icon: typeof FileDashed;
    iconGradient: string;
    titleKey: string;
    bodyKey: string;
    disabled?: boolean;
    badge?: string;
  }[] = [
    {
      value: "blank_template",
      icon: FileDashed,
      iconGradient: "icon-chip-primary",
      titleKey: "create.modeBlankTitle",
      bodyKey: "create.modeBlankBody",
    },
    {
      value: "notes_import",
      icon: NotePencil,
      iconGradient: "icon-chip-success",
      titleKey: "create.modeNotesTitle",
      bodyKey: "create.modeNotesBody",
    },
    {
      value: "profile_import",
      icon: UserCircle,
      iconGradient: "icon-chip-info",
      titleKey: "create.modeProfileTitle",
      bodyKey: "create.modeProfileBody",
    },
    {
      value: "upload",
      icon: UploadSimple,
      iconGradient: "icon-chip-success",
      titleKey: "create.modeUploadTitle",
      bodyKey: "create.modeUploadBody",
    },
    {
      value: "ai_assisted_draft",
      icon: Sparkle,
      iconGradient: "icon-chip-info",
      titleKey: "create.modeAiTitle",
      bodyKey: "create.modeAiBody",
    },
  ];

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
          <Button
            variant="primary"
            onClick={handleCreate}
            loading={submitting}
            disabled={submitDisabled}
          >
            {t("create.submit")}
          </Button>
        </>
      }
    >
      <fieldset>
        <legend className="mb-2 text-sm font-semibold text-[var(--text-primary)]">
          {t("create.chooseMode")}
        </legend>
        <div className="grid gap-2.5 sm:grid-cols-2">
          {modeCards.map((card) => {
            const Icon = card.icon;
            const selected = card.value === mode;
            const onSelect = () => {
              if (card.disabled) return;
              if (card.value === "upload") {
                onClose();
                onOpenUpload();
                return;
              }
              selectMode(card.value as Choosable);
            };
            return (
              <button
                key={card.value}
                type="button"
                onClick={onSelect}
                disabled={card.disabled}
                aria-pressed={selected}
                className={cn(
                  "flex items-start gap-3 rounded-xl border-2 p-3 text-left outline-none transition-colors focus-visible:border-[var(--brand-primary)]",
                  card.disabled
                    ? "cursor-not-allowed border-[var(--border-subtle)] opacity-60"
                    : selected
                      ? "border-[var(--brand-primary)] bg-[var(--blue-50)]"
                      : "border-[var(--border-default)] hover:border-[var(--brand-primary)]/50",
                )}
              >
                <span className={cn("mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg shadow-sm", card.iconGradient)}>
                  <Icon aria-hidden weight="duotone" className="size-4 text-white" />
                </span>
                <span className="min-w-0">
                  <span className="flex items-center gap-1.5">
                    <span className="text-sm font-semibold text-[var(--text-primary)]">
                      {t(card.titleKey)}
                    </span>
                    {card.badge && (
                      <span className="rounded-full bg-[var(--gray-100)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--gray-500)]">
                        {card.badge}
                      </span>
                    )}
                  </span>
                  <span className="mt-0.5 block text-xs text-[var(--text-secondary)]">
                    {t(card.bodyKey)}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </fieldset>

      <div className="mt-5 space-y-4">
        <Input
          label={t("create.titleLabel")}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={t("create.titlePlaceholder")}
          required
          error={error ?? undefined}
        />

        {mode === "notes_import" && (
          <div>
            <Textarea
              label={t("create.notesLabel")}
              value={notes}
              onChange={(e) => {
                setNotes(e.target.value);
                if (notesError) setNotesError(null);
              }}
              placeholder={t("create.notesPlaceholder")}
              rows={7}
              maxLength={NOTES_MAX}
              required
              help={t("create.notesHint")}
              error={notesError ?? undefined}
            />
            <p
              aria-hidden
              className="mt-1 text-right text-xs text-[var(--text-muted)]"
            >
              {notes.length}/{NOTES_MAX}
            </p>
          </div>
        )}

        {mode === "ai_assisted_draft" && (
          <div>
            <Textarea
              label={t("create.aiNotesLabel")}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder={t("create.aiNotesPlaceholder")}
              rows={4}
              maxLength={NOTES_MAX}
              help={t("create.aiNotesHint")}
            />
          </div>
        )}

        <TemplateGallery
          templates={templates.data ?? []}
          selectedId={templateId}
          disabled={templates.isPending}
          onSelect={setTemplateId}
          help={
            mode === "profile_import"
              ? t("create.profileHelp")
              : mode === "notes_import"
                ? t("create.notesTemplateHelp")
                : undefined
          }
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
  help,
}: {
  templates: CvTemplate[];
  selectedId: string;
  disabled?: boolean;
  onSelect: (id: string) => void;
  help?: string;
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
            {help ?? t("create.templateGalleryHint")}
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
            premium={tpl.is_premium}
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
  name,
  category,
  roles = [],
  strengths = [],
  premium,
  selected,
  disabled,
  onClick,
}: {
  name: string;
  category: string;
  roles?: string[];
  strengths?: string[];
  premium?: boolean;
  selected: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  const t = useTranslations("cv");
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
            ? "border-[var(--brand-primary)] bg-[var(--blue-50)]"
            : "border-[var(--border-default)] bg-[var(--surface-card)] hover:border-[var(--brand-primary)]/45",
      )}
    >
      <span
        aria-hidden
        className="relative block aspect-[210/297] w-16 shrink-0 overflow-hidden rounded-md border border-[var(--border-default)] bg-white p-2"
      >
        <span className="block h-1.5 w-3/4 rounded-full bg-[var(--brand-primary)]" />
        <span className="mt-1 block h-1 w-1/2 rounded-full bg-[var(--gray-200)]" />
        <span className="mt-2 block h-px w-full bg-[var(--gray-200)]" />
        {[86, 68, 92, 58, 76].map((w, i) => (
          <span
            key={i}
            className="mt-1 block h-1 rounded-full bg-[var(--gray-100)]"
            style={{ width: `${w}%` }}
          />
        ))}
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
          {selected ? (
            <CheckCircle
              aria-label={t("create.templateSelected")}
              weight="fill"
              className="size-5 shrink-0 text-[var(--brand-primary)]"
            />
          ) : premium ? (
            <Crown
              aria-label={t("create.premium")}
              weight="fill"
              className="size-4 shrink-0 text-[var(--amber-600)]"
            />
          ) : null}
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
