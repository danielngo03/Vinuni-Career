"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Star,
  PencilSimple,
  ChatCircleText,
  ThumbsUp,
  Buildings,
  ChatText,
  Sparkle,
  LightbulbFilament,
} from "@phosphor-icons/react";
import { Button, EmptyState, StatusBadge, useToast } from "@/components/ui";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth-store";
import { useUiStore } from "@/stores/ui-store";
import { reviewsApi, type CompanyRating, type CompanyReview } from "@/lib/api";
import { StarDisplay } from "./star-rating";
import { ReviewWriteModal } from "./review-write-modal";
import { formatDateTime } from "@/lib/format";

const CATEGORY_KEYS = [
  "work_life_balance",
  "culture_values",
  "compensation",
  "career_growth",
  "interview_experience",
] as const;

function deriveReviewInsights(rating: CompanyRating) {
  const cats = CATEGORY_KEYS
    .map((k) => ({ k, v: rating.categories[k] }))
    .filter((x): x is { k: (typeof CATEGORY_KEYS)[number]; v: number } => x.v != null);
  if (cats.length === 0) return null;
  cats.sort((a, b) => b.v - a.v);
  const top = cats[0]!;
  const weak = cats[cats.length - 1]!;
  const avg = rating.overall_avg ?? 0;
  const tier = avg >= 4.5 ? "high" : avg >= 4.0 ? "good" : avg >= 3.0 ? "mixed" : ("low" as const);
  return {
    topKey: top.k,
    topScore: top.v,
    weakKey: top.v - weak.v > 0.4 ? weak.k : null,
    weakScore: weak.v,
    tier,
  } as const;
}

export function CompanyReviewsSection({
  slug,
  rating,
}: {
  slug: string;
  rating: CompanyRating | null;
}) {
  const t = useTranslations("reviews");
  const locale = useLocale();
  const status = useAuthStore((s) => s.status);
  const persona = useAuthStore((s) => s.user?.persona);
  const openLoginModal = useUiStore((s) => s.openLoginModal);
  const qc = useQueryClient();
  const toast = useToast();
  const [writeOpen, setWriteOpen] = useState(false);

  const LIST_KEY = ["reviews", slug, locale] as const;

  const listQuery = useQuery({
    queryKey: LIST_KEY,
    queryFn: () => reviewsApi.listForCompany(slug, locale),
    retry: false,
  });

  // The student's own review (to switch the CTA into "edit"); silent on 404.
  const mineQuery = useQuery({
    queryKey: ["reviews", slug, "mine", locale],
    queryFn: () => reviewsApi.getMine(slug, locale),
    retry: false,
    enabled: status === "authenticated" && persona === "student",
  });
  const myReview = mineQuery.data && !mineQuery.isError ? mineQuery.data : null;

  function handleWriteClick() {
    if (status !== "authenticated") {
      openLoginModal({
        label: t("loginIntent"),
        returnTo: `/companies/${slug}`,
        payload: { intent: "write_review", slug },
      });
      return;
    }
    setWriteOpen(true);
  }

  const [respondingTo, setRespondingTo] = useState<string | null>(null);
  const [responseDraft, setResponseDraft] = useState("");

  const partnerRespondMut = useMutation({
    mutationFn: ({ reviewId, response }: { reviewId: string; response: string }) =>
      reviewsApi.addPartnerResponse(reviewId, response),
    onSuccess: (_, { reviewId }) => {
      qc.setQueryData<{ items: CompanyReview[]; count: number }>(LIST_KEY, (prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          items: prev.items.map((r) =>
            r.id === reviewId
              ? { ...r, partner_response: responseDraft, partner_response_at: new Date().toISOString() }
              : r,
          ),
        };
      });
      toast.show({ tone: "success", title: t("partnerRespondSaved") });
      setRespondingTo(null);
      setResponseDraft("");
    },
    onError: () => toast.show({ tone: "error", title: t("partnerRespondError") }),
  });

  const helpfulMut = useMutation({
    mutationFn: async ({ reviewId, voted }: { reviewId: string; voted: boolean }) => {
      if (voted) return reviewsApi.removeHelpfulVote(reviewId);
      return reviewsApi.voteHelpful(reviewId);
    },
    onSuccess: (res, { reviewId }) => {
      qc.setQueryData<{ items: CompanyReview[]; count: number }>(LIST_KEY, (prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          items: prev.items.map((r) =>
            r.id === reviewId
              ? { ...r, helpful_count: res.helpful_count, my_vote: res.my_vote }
              : r,
          ),
        };
      });
    },
    onError: () => toast.show({ tone: "error", title: t("helpfulError") }),
  });

  function handleHelpful(r: CompanyReview) {
    if (status !== "authenticated") {
      openLoginModal({ label: t("helpfulLoginIntent"), returnTo: `/companies/${slug}` });
      return;
    }
    helpfulMut.mutate({ reviewId: r.id, voted: r.my_vote === true });
  }

  const reviews = listQuery.data?.items ?? [];
  const count = rating?.review_count ?? 0;
  const canWrite = persona === "student" || status !== "authenticated";
  const insights = rating && rating.review_count >= 3 ? deriveReviewInsights(rating) : null;

  return (
    <section className="mt-8" id="reviews">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-lg font-bold tracking-tight text-[var(--text-primary)]">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-lg icon-chip-warning shadow-sm">
            <ChatCircleText aria-hidden weight="duotone" className="size-4 text-white" />
          </span>
          {t("sectionTitle")}
          <span className="rounded-full bg-[var(--bg-subtle)] px-2 py-0.5 text-xs font-semibold text-[var(--text-secondary)]">
            {count}
          </span>
        </h2>
        {canWrite && (
          <Button variant="secondary" onClick={handleWriteClick}>
            {myReview ? (
              <>
                <PencilSimple aria-hidden weight="duotone" className="size-4" />
                {t("editCta")}
              </>
            ) : (
              t("writeCta")
            )}
          </Button>
        )}
      </div>

      {/* AI review insights */}
      {insights && (() => {
        const sentimentKey =
          insights.tier === "high" ? "aiSentimentHigh" :
          insights.tier === "good" ? "aiSentimentGood" :
          insights.tier === "mixed" ? "aiSentimentMixed" :
          "aiSentimentLow";
        return (
          <div className={cn(
            "mb-5 rounded-xl border overflow-hidden shadow-[0_2px_16px_rgba(109,40,217,0.06)]",
            "border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white/60 ",
          )}>
            <div className="flex items-center gap-2 border-b border-[var(--border-default)] px-3.5 py-2.5">
              <span className="flex size-5 shrink-0 items-center justify-center rounded-md icon-chip-info shadow-sm">
                <Sparkle aria-hidden weight="duotone" className="size-3 text-white" />
              </span>
              <span className="text-xs font-bold text-[var(--text-primary)]">{t("aiInsightsTitle")}</span>
            </div>
            <ul className="space-y-2 px-3.5 py-3">
              <li className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                <LightbulbFilament aria-hidden weight="duotone" className="mt-0.5 size-3.5 shrink-0 text-[var(--ai-accent)]" />
                {t("aiStrength", { category: t(`cat.${insights.topKey}`), score: insights.topScore.toFixed(1) })}
              </li>
              {insights.weakKey && (
                <li className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                  <LightbulbFilament aria-hidden weight="duotone" className="mt-0.5 size-3.5 shrink-0 text-[var(--ai-accent)]" />
                  {t("aiImprove", { category: t(`cat.${insights.weakKey}`), score: insights.weakScore.toFixed(1) })}
                </li>
              )}
              <li className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                <LightbulbFilament aria-hidden weight="duotone" className="mt-0.5 size-3.5 shrink-0 text-[var(--ai-accent)]" />
                {t(sentimentKey)}
              </li>
            </ul>
            <div className="border-t border-[var(--border-default)] px-3.5 py-2">
              <p className="text-[0.7rem] text-[var(--text-muted)]">{t("aiDisclaimer")}</p>
            </div>
          </div>
        );
      })()}

      {/* Aggregate */}
      {rating && rating.overall_avg != null ? (
        <div className="mb-5 grid grid-cols-1 gap-4 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4 sm:grid-cols-[auto_1fr]">
          <div className="flex flex-col items-center justify-center gap-1 sm:pr-5 sm:border-r sm:border-[var(--border-subtle)]">
            <span className="text-4xl font-bold text-[var(--text-primary)]">
              {rating.overall_avg.toFixed(1)}
            </span>
            <StarDisplay value={rating.overall_avg} size={18} />
            <span className="text-xs text-[var(--text-muted)]">
              {t("basedOn", { count: rating.review_count })}
            </span>
          </div>
          <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2">
            {CATEGORY_KEYS.map((k) => {
              const v = rating.categories[k];
              if (v == null) return null;
              return (
                <div key={k} className="flex items-center justify-between gap-3">
                  <dt className="text-sm text-[var(--text-secondary)]">
                    {t(`cat.${k}`)}
                  </dt>
                  <dd className="flex items-center gap-1.5">
                    <StarDisplay value={v} size={14} />
                    <span className="w-7 text-right text-sm font-semibold text-[var(--text-primary)]">
                      {v.toFixed(1)}
                    </span>
                  </dd>
                </div>
              );
            })}
          </dl>
        </div>
      ) : null}

      {/* List */}
      {reviews.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {reviews.map((r) => (
            <li
              key={r.id}
              className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4"
            >
              <div className="mb-1.5 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="truncate font-semibold text-[var(--text-primary)]">
                    {r.title}
                  </h3>
                  <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-[var(--text-muted)]">
                    <span>{r.author_name}</span>
                    <StatusBadge tone="verified">{r.trust_label}</StatusBadge>
                  </p>
                </div>
                <span className="flex shrink-0 items-center gap-1 rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-2 py-1 text-sm font-semibold text-[var(--text-primary)] ">
                  <Star
                    aria-hidden
                    weight="fill"
                    className="size-3.5 text-[var(--brand-amber,#d97706)]"
                  />
                  {r.ratings.overall}
                </span>
              </div>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--text-secondary)]">
                {r.body}
              </p>
              {(r.pros || r.cons) && (
                <div className="mt-2.5 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {r.pros && (
                    <p className="rounded-lg bg-[var(--teal-50,#f0fdfa)] px-3 py-2 text-sm text-[var(--text-secondary)]">
                      <span className="font-semibold text-[var(--brand-teal)]">
                        {t("prosLabel")}:{" "}
                      </span>
                      {r.pros}
                    </p>
                  )}
                  {r.cons && (
                    <p className="rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-2 text-sm text-[var(--text-secondary)] ">
                      <span className="font-semibold text-[var(--text-primary)]">
                        {t("consLabel")}:{" "}
                      </span>
                      {r.cons}
                    </p>
                  )}
                </div>
              )}

              {/* Partner response (display) */}
              {r.partner_response && (
                <div className="mt-3 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-2.5">
                  <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-[var(--brand-primary)]">
                    <span className="flex size-4 shrink-0 items-center justify-center rounded icon-chip-primary shadow-sm">
                    <Buildings aria-hidden weight="duotone" className="size-2.5 text-white" />
                  </span>
                    {t("partnerResponseLabel")}
                    {r.partner_response_at && (
                      <span className="ml-1 font-normal text-[var(--text-muted)]">
                        · {formatDateTime(r.partner_response_at, locale)}
                      </span>
                    )}
                  </p>
                  <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
                    {r.partner_response}
                  </p>
                </div>
              )}

              {/* Partner response CTA (partner persona only, no response yet) */}
              {persona === "partner" && !r.partner_response && (
                <div className="mt-3">
                  {respondingTo === r.id ? (
                    <div className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] p-3 ">
                      <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-[var(--brand-primary)]">
                        <span className="flex size-4 shrink-0 items-center justify-center rounded icon-chip-primary shadow-sm">
                    <Buildings aria-hidden weight="duotone" className="size-2.5 text-white" />
                  </span>
                        {t("partnerResponseLabel")}
                      </p>
                      <textarea
                        rows={3}
                        value={responseDraft}
                        onChange={(e) => setResponseDraft(e.target.value)}
                        placeholder={t("partnerRespondPlaceholder")}
                        className="w-full resize-none rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand-primary)]/50 focus:bg-[var(--surface-card)] focus:ring-2 focus:ring-[var(--brand-primary)]/30"
                      />
                      <div className="mt-2 flex items-center justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => { setRespondingTo(null); setResponseDraft(""); }}
                          disabled={partnerRespondMut.isPending}
                        >
                          {t("partnerRespondCancel")}
                        </Button>
                        <Button
                          variant="primary"
                          size="sm"
                          loading={partnerRespondMut.isPending}
                          disabled={!responseDraft.trim() || partnerRespondMut.isPending}
                          onClick={() => partnerRespondMut.mutate({ reviewId: r.id, response: responseDraft.trim() })}
                        >
                          {t("partnerRespondSave")}
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => { setRespondingTo(r.id); setResponseDraft(""); }}
                      className="flex items-center gap-1.5 rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-2.5 py-1.5 text-xs font-semibold text-[var(--brand-primary)] outline-none transition-colors hover:bg-[var(--surface-card)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
                    >
                      <ChatText aria-hidden weight="duotone" className="size-3.5" />
                      {t("partnerRespondCta")}
                    </button>
                  )}
                </div>
              )}

              {/* Helpful footer */}
              <div className="mt-3 flex items-center gap-3 border-t border-[var(--border-default)] pt-2.5">
                <p className="text-xs text-[var(--text-muted)]">
                  {t("helpfulQuestion")}
                </p>
                <button
                  type="button"
                  aria-label={r.my_vote ? t("removeHelpful") : t("markHelpful")}
                  onClick={() => handleHelpful(r)}
                  disabled={helpfulMut.isPending}
                  className={`flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-semibold outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30 ${
                    r.my_vote
                      ? "bg-[var(--brand-primary)] text-white"
                      : "bg-[var(--bg-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-muted)]"
                  }`}
                >
                  <ThumbsUp aria-hidden weight={r.my_vote ? "fill" : "duotone"} className="size-3.5" />
                  {t("helpfulCount", { count: r.helpful_count })}
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState
          kind="empty"
          icon={ChatCircleText}
          title={t("emptyTitle")}
          description={t("emptyBody")}
        />
      )}

      <ReviewWriteModal
        slug={slug}
        open={writeOpen}
        onClose={() => setWriteOpen(false)}
        existing={myReview}
      />
    </section>
  );
}
