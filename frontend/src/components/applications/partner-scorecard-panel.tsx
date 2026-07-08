"use client";

import { useEffect, useId, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardText, ShieldWarning, WarningCircle } from "@phosphor-icons/react";
import { ScorecardAiSuggestButton } from "./scorecard-ai-suggest-button";
import { Button, Modal, StatusBadge, Textarea, useToast } from "@/components/ui";
import { useScorecardLabels } from "@/lib/applications/labels";
import {
  ApiError,
  applicationsApi,
  SCORECARD_CRITERIA,
  SCORECARD_RECOMMENDATIONS,
  type ScorecardListResult,
  type ScorecardRecommendation,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { ScoreScale } from "./scorecard-panel/score-scale";
import { MyScorecardCard } from "./scorecard-panel/my-scorecard-card";
import { AggregateView } from "./scorecard-panel/aggregate-view";
import { minesScoreMap, type ScoreMap } from "./scorecard-panel/utils";

/**
 * Partner-internal scorecard panel (ADR-0005). Lives inside the partner
 * candidate detail drawer. NEVER rendered on any student surface.
 *
 * Anchoring (ADR-0005 §2): before the caller submits their own scorecard for the
 * stage, only the round progress + gate state are shown — other reviewers'
 * scores and the score aggregate stay hidden. After submitting, the aggregate
 * and other reviewers are revealed. This mirrors the backend, which never sends
 * the hidden data; the UI never tries to surface it.
 */
export function PartnerScorecardPanel({
  applicationId,
  canSubmit,
  jobTitle,
}: {
  applicationId: string;
  /** Submitting/editing is only possible while the candidate is under review. */
  canSubmit: boolean;
  jobTitle?: string;
}) {
  const t = useTranslations("scorecards");
  const tc = useTranslations("common");
  const labels = useScorecardLabels();
  const toast = useToast();
  const qc = useQueryClient();
  const apiError = useApiErrorMessage();
  const groupId = useId();

  const scorecardsKey = useMemo(
    () => ["applications", "scorecards", applicationId] as const,
    [applicationId],
  );

  const query = useQuery({
    queryKey: scorecardsKey,
    queryFn: () => applicationsApi.listScorecards(applicationId),
    retry: false,
  });

  const data: ScorecardListResult | undefined = query.data;
  const mine = data?.mine ?? null;

  /* ------------------------------ form state ----------------------------- */
  const [editing, setEditing] = useState(false);
  const [scores, setScores] = useState<ScoreMap>({});
  const [recommendation, setRecommendation] = useState<
    ScorecardRecommendation | ""
  >("");
  const [comment, setComment] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [withdrawOpen, setWithdrawOpen] = useState(false);

  // The form is shown when there is no submitted scorecard yet, or the author
  // chose to edit theirs. A read-only "mine" card is shown otherwise.
  const showForm = canSubmit && (mine === null || editing);

  function resetFormFromMine() {
    setScores(minesScoreMap(mine));
    setRecommendation((mine?.recommendation as ScorecardRecommendation) ?? "");
    setComment(mine?.comment ?? "");
    setFieldError(null);
  }

  // Keep the form blank until the author explicitly edits; pre-fill on edit.
  useEffect(() => {
    if (editing) resetFormFromMine();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing]);

  function invalidateRelated() {
    void qc.invalidateQueries({ queryKey: scorecardsKey });
    void qc.invalidateQueries({
      queryKey: ["applications", "partnerDetail", applicationId],
    });
    // Refresh any open pipeline board so the gate/evaluation reflects the change.
    void qc.invalidateQueries({ queryKey: ["applications", "pipeline"] });
  }

  const submit = useMutation({
    mutationFn: () =>
      applicationsApi.submitScorecard(applicationId, {
        scores: SCORECARD_CRITERIA.map((key) => ({
          criterion_key: key,
          score: scores[key]!,
        })),
        recommendation: recommendation as ScorecardRecommendation,
        comment: comment.trim() || null,
        version: editing ? mine?.version : undefined,
      }),
    onSuccess: (result) => {
      qc.setQueryData(scorecardsKey, result);
      invalidateRelated();
      setEditing(false);
      setFieldError(null);
      toast.show({
        tone: "success",
        title: mine ? t("updatedToast") : t("submittedToast"),
      });
    },
    onError: (e) => {
      if (e instanceof ApiError && e.isValidation) {
        setFieldError(t("validationError"));
        return;
      }
      toast.show({ tone: "error", title: apiError(e) });
    },
  });

  const withdraw = useMutation({
    mutationFn: () =>
      applicationsApi.withdrawScorecard(applicationId, mine!.id),
    onSuccess: (result) => {
      qc.setQueryData(scorecardsKey, result);
      invalidateRelated();
      setWithdrawOpen(false);
      setEditing(false);
      toast.show({ tone: "success", title: t("withdrawnToast") });
    },
    onError: (e) => {
      setWithdrawOpen(false);
      toast.show({ tone: "error", title: apiError(e) });
    },
  });

  const allScored = SCORECARD_CRITERIA.every(
    (k) => typeof scores[k] === "number",
  );
  const canSubmitForm = allScored && recommendation !== "";

  function handleSubmit() {
    if (!canSubmitForm) {
      setFieldError(t("incompleteError"));
      return;
    }
    submit.mutate();
  }

  /* -------------------------------- header ------------------------------- */
  const header = (
    <div className="flex items-center gap-2">
      <span className="flex size-7 shrink-0 items-center justify-center rounded-lg icon-chip-info shadow-sm">
        <ClipboardText aria-hidden weight="duotone" className="size-4 text-white" />
      </span>
      <h3 className="text-base font-bold text-[var(--text-primary)]">
        {t("panelTitle")}
      </h3>
    </div>
  );

  /* ------------------------------- states -------------------------------- */
  if (query.isPending) {
    return (
      <section aria-label={t("panelTitle")} className="space-y-3">
        {header}
        <div
          className="h-28 animate-pulse rounded-xl bg-[var(--bg-muted)]"
          aria-hidden
        />
      </section>
    );
  }

  if (query.isError || !data) {
    return (
      <section aria-label={t("panelTitle")} className="space-y-3">
        {header}
        <div className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] p-3.5 ">
          <p className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
            <WarningCircle
              aria-hidden
              weight="duotone"
              className="size-4 text-[var(--text-muted)]"
            />
            {t("loadError")}
          </p>
          <Button
            variant="secondary"
            size="sm"
            className="mt-2"
            onClick={() => query.refetch()}
          >
            {tc("retry")}
          </Button>
        </div>
      </section>
    );
  }

  // Not in a review stage yet (pre-pipeline) — scorecards do not apply.
  if (data.stage_id === null) {
    return (
      <section aria-label={t("panelTitle")} className="space-y-3">
        {header}
        <div className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] p-3.5 ">
          <p className="text-sm text-[var(--text-secondary)]">
            {t("notInStageBody")}
          </p>
        </div>
      </section>
    );
  }

  const agg = data.aggregate;
  const submitted = agg.submitted_count;
  const required = agg.required;
  const gateApplies = required > 0;

  return (
    <section aria-label={t("panelTitle")} className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        {header}
        <span className="text-xs font-medium text-[var(--text-muted)]">
          {t("partnerOnly")}
        </span>
      </div>

      {/* Round progress + gate state (always visible; anchoring-safe). */}
      <div className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] p-3.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            {t("progress", { count: submitted })}
          </p>
          {gateApplies &&
            (agg.gate_met ? (
              <StatusBadge tone="accepted">{t("gateMet")}</StatusBadge>
            ) : (
              <StatusBadge tone="pending">{t("gateRequired")}</StatusBadge>
            ))}
        </div>
        {gateApplies && !agg.gate_met && (
          <p className="mt-1.5 flex items-start gap-1.5 text-xs text-[var(--amber-700)]">
            <WarningCircle
              aria-hidden
              weight="duotone"
              className="mt-0.5 size-3.5 shrink-0"
            />
            {t("gateHint")}
          </p>
        )}
        {/* Anchoring notice — only while peers' scores are still hidden. */}
        {mine === null && submitted > 0 && (
          <p className="mt-1.5 flex items-start gap-1.5 text-xs text-[var(--text-muted)]">
            <ShieldWarning
              aria-hidden
              weight="duotone"
              className="mt-0.5 size-3.5 shrink-0"
            />
            {t("anchoringNote")}
          </p>
        )}
      </div>

      {/* Read-only "mine" card with edit / withdraw. */}
      {mine !== null && !editing && (
        <MyScorecardCard
          mine={mine}
          canSubmit={canSubmit}
          onEdit={() => setEditing(true)}
          onWithdraw={() => setWithdrawOpen(true)}
        />
      )}

      {/* Submit / edit form. */}
      {showForm && (
        <div className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] p-3.5">
          <div className="mb-3 flex items-center justify-between gap-2">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {mine ? t("editTitle") : t("formTitle")}
            </p>
            <ScorecardAiSuggestButton
              applicationId={applicationId}
              jobTitle={jobTitle}
              onApply={(aiScores, aiRec, aiReasoning) => {
                setScores((prev) => ({ ...prev, ...aiScores }));
                if (aiRec) setRecommendation(aiRec);
                if (aiReasoning) {
                  setComment((prev) =>
                    prev ? `${aiReasoning}\n\n${prev}` : aiReasoning,
                  );
                }
                setFieldError(null);
              }}
            />
          </div>

          <div className="space-y-3">
            {SCORECARD_CRITERIA.map((key) => (
              <ScoreScale
                key={key}
                name={`${groupId}-${key}`}
                legend={labels.criterion(key)}
                value={scores[key] ?? null}
                disabled={submit.isPending}
                onChange={(n) => {
                  setScores((prev) => ({ ...prev, [key]: n }));
                  setFieldError(null);
                }}
              />
            ))}
          </div>

          <fieldset
            className="mt-4"
            disabled={submit.isPending}
            aria-describedby={fieldError ? `${groupId}-err` : undefined}
          >
            <legend className="mb-1.5 text-sm font-semibold text-[var(--text-primary)]">
              {t("recommendationLabel")}
              <span className="ml-0.5 text-[var(--brand-red)]" aria-hidden>
                *
              </span>
            </legend>
            <div
              role="radiogroup"
              aria-label={t("recommendationLabel")}
              className="grid grid-cols-2 gap-2 sm:grid-cols-4"
            >
              {SCORECARD_RECOMMENDATIONS.map((rec) => {
                const id = `${groupId}-rec-${rec}`;
                const checked = recommendation === rec;
                return (
                  <label
                    key={rec}
                    htmlFor={id}
                    className="relative cursor-pointer"
                  >
                    <input
                      type="radio"
                      id={id}
                      name={`${groupId}-rec`}
                      value={rec}
                      checked={checked}
                      onChange={() => {
                        setRecommendation(rec);
                        setFieldError(null);
                      }}
                      className="peer sr-only"
                    />
                    <span className="flex items-center justify-center rounded-lg border border-[var(--border-default)] bg-[var(--bg-subtle)] px-2 py-2 text-center text-xs font-semibold text-[var(--text-secondary)] transition-colors peer-checked:border-[var(--brand-primary)] peer-checked:bg-[var(--brand-primary)]/10 peer-checked:text-[var(--brand-primary)] peer-focus-visible:ring-2 peer-focus-visible:ring-[var(--brand-primary)]/40">
                      {labels.recommendation(rec)}
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          <div className="mt-4">
            <Textarea
              label={t("commentLabel")}
              rows={3}
              maxLength={5000}
              value={comment}
              disabled={submit.isPending}
              placeholder={t("commentPlaceholder")}
              help={t("commentHelp")}
              onChange={(e) => setComment(e.target.value)}
            />
          </div>

          {fieldError && (
            <p
              id={`${groupId}-err`}
              role="alert"
              className="mt-2 text-xs font-medium text-[var(--brand-red)]"
            >
              {fieldError}
            </p>
          )}

          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              variant="primary"
              size="sm"
              loading={submit.isPending}
              disabled={!canSubmitForm}
              onClick={handleSubmit}
            >
              {mine ? t("save") : t("submit")}
            </Button>
            {mine !== null && (
              <Button
                variant="ghost"
                size="sm"
                disabled={submit.isPending}
                onClick={() => {
                  setEditing(false);
                  setFieldError(null);
                }}
              >
                {tc("cancel")}
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Aggregate + other reviewers — revealed only after the caller submits. */}
      {mine !== null && (
        <AggregateView
          data={data}
          criterionLabel={(k, l) => labels.criterion(k, l)}
          recommendationLabel={(r) => labels.recommendation(r)}
        />
      )}

      {/* Withdraw confirmation — Modal, never confirm(). */}
      <Modal
        open={withdrawOpen}
        onClose={() => (withdraw.isPending ? undefined : setWithdrawOpen(false))}
        title={t("withdrawTitle")}
        description={t("withdrawBody")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => setWithdrawOpen(false)}
              disabled={withdraw.isPending}
            >
              {tc("cancel")}
            </Button>
            <Button
              variant="danger"
              loading={withdraw.isPending}
              onClick={() => withdraw.mutate()}
            >
              {t("withdrawConfirm")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">
          {t("withdrawNote")}
        </p>
      </Modal>
    </section>
  );
}
