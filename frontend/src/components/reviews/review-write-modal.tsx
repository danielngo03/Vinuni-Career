"use client";

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Input, Modal, Switch, Textarea, useToast } from "@/components/ui";
import { StarInput } from "./star-rating";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import {
  ApiError,
  reviewsApi,
  type OwnReview,
  type ReviewRatings,
} from "@/lib/api";

const CATEGORIES: { key: keyof ReviewRatings; optional?: boolean }[] = [
  { key: "overall" },
  { key: "work_life_balance" },
  { key: "culture_values" },
  { key: "compensation" },
  { key: "career_growth" },
  { key: "interview_experience", optional: true },
];

const EMPTY: ReviewRatings = {
  overall: 0,
  work_life_balance: 0,
  culture_values: 0,
  compensation: 0,
  career_growth: 0,
  interview_experience: null,
};

export function ReviewWriteModal({
  slug,
  open,
  onClose,
  existing,
}: {
  slug: string;
  open: boolean;
  onClose: () => void;
  /** When set, the modal edits this review instead of creating a new one. */
  existing?: OwnReview | null;
}) {
  const t = useTranslations("reviews");
  const tc = useTranslations("common");
  const locale = useLocale();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [pros, setPros] = useState("");
  const [cons, setCons] = useState("");
  const [anonymous, setAnonymous] = useState(false);
  const [ratings, setRatings] = useState<ReviewRatings>(EMPTY);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setError(null);
      if (existing) {
        setTitle(existing.title);
        setBody(existing.body);
        setPros(existing.pros ?? "");
        setCons(existing.cons ?? "");
        setAnonymous(existing.is_anonymous);
        setRatings(existing.ratings);
      } else {
        setTitle("");
        setBody("");
        setPros("");
        setCons("");
        setAnonymous(false);
        setRatings(EMPTY);
      }
    }
  }, [open, existing]);

  const mutation = useMutation({
    mutationFn: () => {
      const payload = {
        title,
        body,
        pros: pros || null,
        cons: cons || null,
        is_anonymous: anonymous,
        ratings,
        ...(existing ? { version: existing.version } : {}),
      };
      return existing
        ? reviewsApi.update(existing.id, payload, locale)
        : reviewsApi.submit(slug, payload, locale);
    },
    onSuccess: () => {
      toast.show({
        tone: "success",
        title: existing ? t("updatedToast") : t("submittedToast"),
        description: t("pendingNote"),
      });
      void qc.invalidateQueries({ queryKey: ["reviews", slug] });
      void qc.invalidateQueries({ queryKey: ["companies", "detail", slug] });
      onClose();
    },
    onError: (e: unknown) => {
      if (e instanceof ApiError && e.isPermissionError) {
        setError(t("ineligibleBody"));
        return;
      }
      setError(getMessage(e));
    },
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!title.trim()) return setError(t("errTitle"));
    if (body.trim().length < 50) return setError(t("errBody"));
    for (const c of CATEGORIES) {
      if (!c.optional && !ratings[c.key]) return setError(t("errRatings"));
    }
    mutation.mutate();
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={existing ? t("editTitle") : t("writeTitle")}
      size="md"
      closeLabel={tc("close")}
    >
      <form onSubmit={submit} className="space-y-4">
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
          {CATEGORIES.map((c) => (
            <div
              key={c.key}
              className="flex items-center justify-between gap-3 rounded-xl border border-white/50 bg-white/70 px-3 py-2 backdrop-blur-sm"
            >
              <span className="text-sm text-[var(--text-secondary)]">
                {t(`cat.${c.key}`)}
                {c.optional && (
                  <span className="ml-1 text-xs text-[var(--text-muted)]">
                    ({tc("optional")})
                  </span>
                )}
              </span>
              <StarInput
                label={t(`cat.${c.key}`)}
                value={ratings[c.key] ?? 0}
                onChange={(v) => setRatings((r) => ({ ...r, [c.key]: v }))}
              />
            </div>
          ))}
        </div>

        <div>
          <label
            htmlFor="rv-title"
            className="mb-1 block text-sm font-semibold text-[var(--text-primary)]"
          >
            {t("fieldTitle")}
          </label>
          <Input
            id="rv-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={300}
            placeholder={t("titlePlaceholder")}
          />
        </div>

        <div>
          <label
            htmlFor="rv-body"
            className="mb-1 block text-sm font-semibold text-[var(--text-primary)]"
          >
            {t("fieldBody")}
          </label>
          <Textarea
            id="rv-body"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={4}
            maxLength={5000}
            placeholder={t("bodyPlaceholder")}
          />
          <p className="mt-1 text-xs text-[var(--text-muted)]">{t("bodyHint")}</p>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Textarea
            aria-label={t("fieldPros")}
            value={pros}
            onChange={(e) => setPros(e.target.value)}
            rows={2}
            maxLength={5000}
            placeholder={t("prosPlaceholder")}
          />
          <Textarea
            aria-label={t("fieldCons")}
            value={cons}
            onChange={(e) => setCons(e.target.value)}
            rows={2}
            maxLength={5000}
            placeholder={t("consPlaceholder")}
          />
        </div>

        <div className="rounded-xl border border-white/50 bg-white/70 px-3 py-2.5 backdrop-blur-sm">
          <Switch
            checked={anonymous}
            onCheckedChange={setAnonymous}
            label={t("anonymousLabel")}
          />
        </div>

        <p className="rounded-xl border border-white/50 bg-white/70 px-3 py-2 text-xs text-[var(--text-secondary)] backdrop-blur-sm">
          {t("moderationNote")}
        </p>

        {error && (
          <p className="rounded-xl bg-[var(--red-50)] px-3 py-2 text-sm text-[var(--brand-red)]">
            {error}
          </p>
        )}

        <div className="flex items-center justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button type="submit" loading={mutation.isPending}>
            {existing ? tc("save") : t("submitCta")}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
