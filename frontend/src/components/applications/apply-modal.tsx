"use client";

import { useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle,
  FileText,
  Info,
  ShieldCheck,
  Sparkle,
  Warning,
  WarningCircle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import {
  Button,
  EmptyState,
  Modal,
  Select,
  Skeleton,
  Switch,
  useToast,
} from "@/components/ui";
import {
  ApiError,
  applicationsApi,
  coverLetterApi,
  cvApi,
  newIdempotencyKey,
  type JobFitResult,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { formatDateTime } from "@/lib/format";
import { useAuthStore } from "@/stores/auth-store";
import { FIT_TIER_TEXT, fitTier } from "@/lib/cv/fit";

type Phase = "form" | "submitting" | "success" | "duplicate" | "gone";

export function ApplyModal({
  open,
  onClose,
  jobId,
  jobTitle,
  cvLanguageRequired,
}: {
  open: boolean;
  onClose: () => void;
  jobId: string;
  jobTitle: string;
  /**
   * CV language preference from the job posting. When "en" or "vi", the modal
   * shows a soft warning if the selected CV is in a different language.
   * Undefined / "any" = no warning shown.
   */
  cvLanguageRequired?: "any" | "en" | "vi";
}) {
  const t = useTranslations("apply");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");
  const tFit = useTranslations("cvFit");
  const locale = useLocale();
  const toast = useToast();
  const apiError = useApiErrorMessage();
  const persona = useAuthStore((s) => s.user?.persona);
  const isStudent = persona === "student";

  const [phase, setPhase] = useState<Phase>("form");
  const [cvId, setCvId] = useState<string>("");
  const [versionId, setVersionId] = useState<string>("");
  const [coverLetter, setCoverLetter] = useState("");
  const [coverLetterAiLoading, setCoverLetterAiLoading] = useState(false);
  const [coverLetterAiFallback, setCoverLetterAiFallback] = useState(false);
  const [anonymous, setAnonymous] = useState(false);
  const [idempotencyKey, setIdempotencyKey] = useState("");

  // Fresh idempotency key + clean form each time the modal opens.
  useEffect(() => {
    if (open) {
      setIdempotencyKey(newIdempotencyKey());
      setPhase("form");
      setCoverLetter("");
      setCoverLetterAiFallback(false);
      setAnonymous(false);
    }
  }, [open]);

  const cvList = useQuery({
    queryKey: ["cv", "list", "apply"],
    queryFn: () => cvApi.list({ limit: 50 }),
    enabled: open,
    retry: false,
  });

  // Only library (`ready`) CVs can be used to apply — drafts are unlimited
  // scratch and are never selectable here (backend rejects applying with a
  // non-`ready` CV; we filter client-side so the picker never offers one).
  const cvs = useMemo(
    () => (cvList.data?.data ?? []).filter((c) => c.status === "ready"),
    [cvList.data],
  );

  // CV-to-job fit (owner-scoped). Drives ordering, per-option score, and the
  // recommended default. Read-only enrichment — never blocks applying.
  const fit = useQuery({
    queryKey: ["cv", "job-fit", jobId],
    queryFn: () => cvApi.jobFit(jobId),
    enabled: open && isStudent,
    retry: false,
    staleTime: 60_000,
  });

  const fitByCv = useMemo(() => {
    const map = new Map<string, JobFitResult>();
    for (const r of fit.data?.results ?? []) map.set(r.cv_id, r);
    return map;
  }, [fit.data]);

  const recommendedId = fit.data?.recommended_cv_id ?? null;

  // Order CVs by fit score (desc) when scores exist; unscored CVs go last.
  const orderedCvs = useMemo(() => {
    if (!fit.data) return cvs;
    const scoreOf = (id: string) => fitByCv.get(id)?.score ?? -1;
    return [...cvs].sort((a, b) => scoreOf(b.id) - scoreOf(a.id));
  }, [cvs, fit.data, fitByCv]);

  // Fit is settled once it has resolved, errored, or is not applicable (so a
  // slow/failed fit call never blocks the apply form's CV default).
  const fitReady = !isStudent || fit.isFetched || fit.isError;

  // Default-select the recommended CV, else the first available CV — once ready.
  useEffect(() => {
    if (cvId || cvs.length === 0 || !fitReady) return;
    const recommended = recommendedId
      ? cvs.find((c) => c.id === recommendedId)
      : undefined;
    setCvId((recommended ?? cvs[0]!).id);
  }, [cvs, cvId, fitReady, recommendedId]);

  const cvDetail = useQuery({
    queryKey: ["cv", "detail", cvId, "apply"],
    queryFn: () => cvApi.get(cvId),
    enabled: open && !!cvId,
    retry: false,
  });

  // Default the version to the current snapshot whenever the CV changes.
  const detail = cvDetail.data;
  useEffect(() => {
    if (detail) {
      setVersionId(detail.current_version_id ?? detail.versions?.[0]?.id ?? "");
    }
  }, [detail]);

  const versions = useMemo(() => detail?.versions ?? [], [detail]);

  async function generateCoverLetterDraft() {
    setCoverLetterAiLoading(true);
    try {
      const result = await coverLetterApi.generate(jobId);
      setCoverLetter(result.draft);
      setCoverLetterAiFallback(result.is_fallback);
    } catch {
      toast.show({ tone: "error", title: t("coverLetterAiError") });
    } finally {
      setCoverLetterAiLoading(false);
    }
  }

  async function handleSubmit() {
    if (!versionId) return;
    setPhase("submitting");
    try {
      await applicationsApi.apply({
        job_id: jobId,
        cv_selection: {
          type: "builder_cv",
          cv_profile_id: cvId,
          cv_version_id: versionId,
        },
        cover_letter: coverLetter.trim() || null,
        is_anonymous: anonymous,
        idempotency_key: idempotencyKey,
      });
      setPhase("success");
    } catch (e) {
      if (e instanceof ApiError) {
        const reason =
          typeof e.details?.reason === "string" ? e.details.reason : undefined;
        if (e.code === "CONFLICT" || reason === "duplicate_application") {
          setPhase("duplicate");
          return;
        }
        if (e.isNotFound) {
          setPhase("gone");
          return;
        }
      }
      setPhase("form");
      toast.show({ tone: "error", title: apiError(e) });
    }
  }

  const submitting = phase === "submitting";

  /* ----------------------------- Result states ---------------------------- */
  if (phase === "success" || phase === "duplicate" || phase === "gone") {
    const isErr = phase === "gone";
    return (
      <Modal
        open={open}
        onClose={onClose}
        title={
          phase === "success"
            ? t("successTitle")
            : phase === "duplicate"
              ? t("duplicateTitle")
              : t("goneTitle")
        }
        size="sm"
        closeLabel={tc("close")}
        footer={
          phase === "gone" ? (
            <Button variant="primary" onClick={onClose}>
              {tc("close")}
            </Button>
          ) : (
            <>
              <Button variant="ghost" onClick={onClose}>
                {tc("close")}
              </Button>
              <Link href="/student/applications" onClick={onClose}>
                <Button variant="primary">{t("viewApplications")}</Button>
              </Link>
            </>
          )
        }
      >
        <div className="flex flex-col items-center gap-3 py-4 text-center">
          <span
            className={
              isErr
                ? "flex size-12 items-center justify-center rounded-2xl icon-chip-danger shadow-[0_4px_16px_rgba(239,68,68,0.30)]"
                : "flex size-12 items-center justify-center rounded-2xl icon-chip-success shadow-[0_4px_16px_rgba(20,184,166,0.30)]"
            }
          >
            {isErr ? (
              <WarningCircle
                aria-hidden
                weight="duotone"
                className="size-7 text-white"
              />
            ) : (
              <CheckCircle
                aria-hidden
                weight="duotone"
                className="size-7 text-white"
              />
            )}
          </span>
          <p className="text-sm text-[var(--text-secondary)]">
            {phase === "success"
              ? t("successBody", { job: jobTitle })
              : phase === "duplicate"
                ? t("duplicateBody")
                : t("goneBody")}
          </p>
        </div>
      </Modal>
    );
  }

  /* -------------------------------- Form ---------------------------------- */
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t("title")}
      description={t("subtitle", { job: jobTitle })}
      size="md"
      closeLabel={tc("close")}
      footer={
        cvs.length > 0 ? (
          <>
            <Button variant="ghost" onClick={onClose} disabled={submitting}>
              {tc("cancel")}
            </Button>
            <Button
              variant="primary"
              loading={submitting}
              disabled={!versionId || submitting}
              onClick={handleSubmit}
            >
              {t("submit")}
            </Button>
          </>
        ) : undefined
      }
    >
      {cvList.isPending ? (
        <div className="space-y-3">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : cvList.isError ? (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={tStates("errorTitle")}
          description={tStates("errorBody")}
          action={
            <Button variant="secondary" onClick={() => cvList.refetch()}>
              {tc("retry")}
            </Button>
          }
        />
      ) : cvs.length === 0 ? (
        <EmptyState
          kind="empty"
          icon={FileText}
          title={t("noReadyCvTitle")}
          description={t("noReadyCvBody")}
          action={
            <Link href="/student/cv" onClick={onClose}>
              <Button variant="primary">{t("goToCvStudio")}</Button>
            </Link>
          }
        />
      ) : (
        <div className="space-y-5">
          {/* CV selection — ordered by fit score, recommended CV tagged */}
          <div>
            <Select
              label={t("cvLabel")}
              required
              value={cvId}
              onChange={(e) => setCvId(e.target.value)}
              options={orderedCvs.map((c) => {
                const f = fitByCv.get(c.id);
                const langLabel = c.language
                  ? ` [${c.language.toUpperCase()}]`
                  : "";
                const parts = [c.title + langLabel];
                if (f) parts.push(tFit("applyScoreLabel", { score: f.score }));
                if (recommendedId === c.id) parts.push(tFit("recommendedTag"));
                return { value: c.id, label: parts.join(" · ") };
              })}
              help={t("cvHelp")}
            />
            <SelectedCvFit fit={fitByCv.get(cvId)} />
            <CvLanguageMismatchWarning
              cvLanguageRequired={cvLanguageRequired}
              selectedCvLanguage={orderedCvs.find((c) => c.id === cvId)?.language}
              locale={locale}
            />
          </div>

          {/* Version selection */}
          {cvDetail.isPending ? (
            <Skeleton className="h-10 w-full" />
          ) : cvDetail.isError ? (
            <p
              role="alert"
              className="text-xs font-medium text-[var(--brand-red)]"
            >
              {t("versionError")}
            </p>
          ) : versions.length > 0 ? (
            <Select
              label={t("versionLabel")}
              required
              value={versionId}
              onChange={(e) => setVersionId(e.target.value)}
              options={versions.map((v) => ({
                value: v.id,
                label: `v${v.version}${v.is_current ? ` · ${t("current")}` : ""} · ${
                  v.change_summary ||
                  formatDateTime(v.created_at ?? null, locale)
                }`,
              }))}
              help={t("versionHelp")}
            />
          ) : null}

          {/* Cover letter */}
          <div>
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <label
                htmlFor="apply-cover-letter"
                className="text-sm font-semibold text-[var(--text-primary)]"
              >
                {t("coverLetterLabel")}
              </label>
              {isStudent && (
                <button
                  type="button"
                  disabled={coverLetterAiLoading}
                  onClick={generateCoverLetterDraft}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--ai-accent)]/40 bg-[var(--ai-accent-soft)] px-2.5 py-1 text-xs font-semibold text-[var(--ai-accent)] outline-none transition-colors hover:border-[var(--ai-accent)]/70 hover:bg-[var(--ai-accent-soft)]/80 focus-visible:ring-2 focus-visible:ring-[var(--ai-accent)]/30 disabled:opacity-60"
                >
                  {coverLetterAiLoading ? (
                    <span className="h-3 w-3 animate-spin rounded-full border-2 border-[var(--ai-accent)]/30 border-t-[var(--ai-accent)]" />
                  ) : (
                    <Sparkle aria-hidden weight="fill" className="size-3.5" />
                  )}
                  {t("coverLetterAiDraft")}
                </button>
              )}
            </div>
            <textarea
              id="apply-cover-letter"
              value={coverLetter}
              onChange={(e) => setCoverLetter(e.target.value)}
              rows={4}
              maxLength={5000}
              placeholder={t("coverLetterPlaceholder")}
              className="w-full rounded-xl border border-[var(--glass-border)] bg-[var(--glass-surface)] backdrop-blur-sm px-3.5 py-2.5 text-sm text-[var(--text-primary)] outline-none transition-colors placeholder:text-[var(--text-muted)] focus:border-[var(--brand-primary)]/50 focus:bg-[var(--glass-surface-heavy)] focus:ring-2 focus:ring-[var(--brand-primary)]/30"
            />
            {coverLetter && (
              <p className="mt-1.5 flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
                <Warning aria-hidden weight="duotone" className="size-3.5 shrink-0 text-[var(--amber-600,#d97706)]" />
                {coverLetterAiFallback ? t("coverLetterAiDisclaimerFallback") : t("coverLetterAiDisclaimer")}
              </p>
            )}
          </div>

          {/* Anonymous toggle */}
          <div className="rounded-xl border border-[var(--glass-border)] bg-[var(--glass-surface-light)] p-3.5 backdrop-blur-sm">
            <Switch
              id="apply-anonymous"
              checked={anonymous}
              onCheckedChange={setAnonymous}
              label={t("anonymousLabel")}
            />
            <p className="mt-2 flex items-start gap-2 text-xs text-[var(--text-secondary)]">
              <ShieldCheck
                aria-hidden
                weight="duotone"
                className="mt-0.5 size-4 shrink-0 text-[var(--brand-primary)]"
              />
              {t("anonymousHint")}
            </p>
          </div>

          <p className="flex items-start gap-2 text-xs text-[var(--text-muted)]">
            <Info aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0" />
            {t("snapshotHint")}
          </p>
        </div>
      )}
    </Modal>
  );
}

/**
 * Soft language-mismatch warning. Renders only when the job has a specific CV
 * language preference ("en" or "vi") and the selected CV is in a different
 * language. This is advisory only — never blocks applying.
 */
function CvLanguageMismatchWarning({
  cvLanguageRequired,
  selectedCvLanguage,
  locale,
}: {
  cvLanguageRequired?: "any" | "en" | "vi";
  selectedCvLanguage?: string | null;
  locale: string;
}) {
  if (
    !cvLanguageRequired ||
    cvLanguageRequired === "any" ||
    !selectedCvLanguage
  )
    return null;

  const required = cvLanguageRequired.toLowerCase();
  const selected = selectedCvLanguage.toLowerCase();
  if (required === selected) return null;

  const isVi = locale === "vi";
  const langName = (code: string) =>
    code === "en"
      ? isVi
        ? "Tiếng Anh"
        : "English"
      : isVi
        ? "Tiếng Việt"
        : "Vietnamese";

  const message = isVi
    ? `Vị trí này ưu tiên CV bằng ${langName(required)} — CV bạn chọn đang ở ${langName(selected)}.`
    : `This position prefers CVs in ${langName(required)} — your selected CV is in ${langName(selected)}.`;

  return (
    <p
      role="status"
      className="mt-2 flex items-start gap-1.5 text-xs leading-relaxed text-amber-600 dark:text-amber-400"
    >
      <Warning
        aria-hidden
        weight="duotone"
        className="mt-0.5 size-3.5 shrink-0"
      />
      {message}
    </p>
  );
}

/**
 * Compact fit readout for the CV currently selected in the apply picker. Shows
 * the product fit score + tier and a stale warning so the student can confirm
 * the right CV before submitting. Renders nothing when there's no fit data
 * (guest/partner, fit offline, or unscored CV) — applying is never blocked.
 */
function SelectedCvFit({ fit }: { fit: JobFitResult | undefined }) {
  const tFit = useTranslations("cvFit");
  if (!fit) return null;
  const tier = fitTier(fit.score);
  return (
    <div className="mt-2 space-y-1.5">
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        <span
          className="font-semibold tabular-nums"
          style={{ color: FIT_TIER_TEXT[tier] }}
        >
          {tFit("applyScoreLabel", { score: fit.score })}
        </span>
        <span
          className="rounded-full px-2 py-0.5 font-semibold"
          style={{
            color: FIT_TIER_TEXT[tier],
            backgroundColor: "var(--bg-subtle)",
          }}
        >
          {tFit(`tier.${tier}` as "tier.strong")}
        </span>
      </p>
      {fit.stale && (
        <p className="flex items-start gap-1.5 text-xs leading-relaxed text-[var(--amber-700)]">
          <WarningCircle
            aria-hidden
            weight="duotone"
            className="mt-0.5 size-3.5 shrink-0"
          />
          <span>
            <span className="font-semibold">{tFit("staleTitle")}</span>{" "}
            {tFit("staleBody", { days: fit.last_updated_days })}
          </span>
        </p>
      )}
    </div>
  );
}
