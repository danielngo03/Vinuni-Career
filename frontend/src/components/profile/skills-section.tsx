"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Lightning, Plus, Sparkle, X } from "@phosphor-icons/react";
import { Button, useToast } from "@/components/ui";
import { ApiError, profileApi, type SkillItem } from "@/lib/api";
import { SkillEditModal } from "./skill-edit-modal";
import { ConfirmDeleteModal } from "./confirm-delete-modal";
import { useProfileMutations } from "./use-profile-mutations";

export function SkillsSection({ items }: { items: SkillItem[] }) {
  const t = useTranslations("profile.skills");
  const toast = useToast();
  const { reloadProfile, handleError } = useProfileMutations();

  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState<SkillItem | null>(null);
  const [toDelete, setToDelete] = useState<SkillItem | null>(null);
  const [suggestEnabled, setSuggestEnabled] = useState(false);

  const existingNames = new Set(items.map((s) => s.name?.toLowerCase() ?? ""));

  const add = useMutation({
    mutationFn: (name: string) => profileApi.createSkill({ name }),
    onSuccess: () => {
      setDraft("");
      reloadProfile();
    },
    onError: (error) => {
      if (
        error instanceof ApiError &&
        error.details?.reason === "duplicate_skill"
      ) {
        toast.show({ tone: "warning", title: t("duplicate") });
        return;
      }
      handleError(error);
    },
  });

  const del = useMutation({
    mutationFn: (id: string) => profileApi.deleteChild("skills", id),
    onSuccess: () => {
      reloadProfile();
      setToDelete(null);
    },
    onError: (e) => {
      handleError(e);
      setToDelete(null);
    },
  });

  const suggestions = useQuery({
    queryKey: ["ai-skill-suggestions"],
    queryFn: () => profileApi.getAiSkillSuggestions(),
    enabled: suggestEnabled,
    staleTime: 5 * 60 * 1000,
  });

  const submitDraft = () => {
    const name = draft.trim();
    if (name && !add.isPending) add.mutate(name);
  };

  const addSuggestion = (name: string) => {
    if (!add.isPending) add.mutate(name);
  };

  // Suggestions filtered to exclude skills already added
  const visibleSuggestions =
    suggestEnabled && suggestions.data
      ? suggestions.data.suggestions.filter(
          (s) => !existingNames.has(s.toLowerCase()),
        )
      : [];

  return (
    <section className="rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] p-6 shadow-[0_2px_12px_rgba(11,34,57,0.06)] backdrop-blur-md">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-xl icon-chip-warning shadow-sm">
            <Lightning aria-hidden weight="duotone" className="size-4 text-white" />
          </span>
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              {t("title")}
            </h2>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">{t("intro")}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setSuggestEnabled(true)}
          disabled={suggestEnabled && suggestions.isFetching}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-[var(--ai-accent)]/40 bg-[var(--ai-accent-soft)] px-3 py-1.5 text-xs font-semibold text-[var(--ai-accent)] outline-none transition-colors hover:bg-[var(--ai-accent)]/15 focus-visible:ring-2 focus-visible:ring-[var(--ai-accent)]/40 disabled:opacity-60"
          aria-label={t("aiSuggestAria")}
        >
          {suggestEnabled && suggestions.isFetching ? (
            <span className="size-3.5 animate-spin rounded-full border-2 border-[var(--ai-accent)]/30 border-t-[var(--ai-accent)]" />
          ) : (
            <Sparkle aria-hidden weight="fill" className="size-3.5" />
          )}
          {t("aiSuggest")}
        </button>
      </div>

      <div className="mt-5 flex gap-2">
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              submitDraft();
            }
          }}
          aria-label={t("addPlaceholder")}
          placeholder={t("addPlaceholder")}
          maxLength={100}
          className="w-full rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] backdrop-blur-sm px-3.5 py-2.5 text-sm font-medium text-[var(--text-primary)] outline-none transition-colors placeholder:text-[var(--text-muted)] focus:border-[var(--brand-primary)]/50 focus:bg-[var(--glass-surface-heavy)] focus:ring-2 focus:ring-[var(--brand-primary)]/30"
        />
        <Button
          variant="secondary"
          loading={add.isPending}
          disabled={!draft.trim()}
          onClick={submitDraft}
        >
          <Plus aria-hidden weight="bold" className="size-4" />
          {t("add")}
        </Button>
      </div>

      {/* AI suggestions row */}
      {suggestEnabled && (
        <div className="mt-3">
          {suggestions.isError ? (
            <p className="text-xs text-[var(--brand-red)]">{t("aiSuggestError")}</p>
          ) : visibleSuggestions.length > 0 ? (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs font-medium text-[var(--text-muted)]">
                {suggestions.data?.is_fallback ? t("aiSuggestFallbackLabel") : t("aiSuggestLabel")}
              </span>
              {visibleSuggestions.map((name) => (
                <button
                  key={name}
                  type="button"
                  onClick={() => addSuggestion(name)}
                  disabled={add.isPending}
                  className="inline-flex items-center gap-1 rounded-full border border-[var(--ai-accent)]/30 bg-[var(--ai-accent-soft)] px-2.5 py-0.5 text-xs font-medium text-[var(--ai-accent)] transition-colors hover:border-[var(--ai-accent)]/60 hover:bg-[var(--ai-accent)]/15 disabled:opacity-50"
                >
                  <Plus aria-hidden weight="bold" className="size-2.5" />
                  {name}
                </button>
              ))}
            </div>
          ) : suggestions.isSuccess && visibleSuggestions.length === 0 ? (
            <p className="text-xs text-[var(--text-muted)]">{t("aiSuggestEmpty")}</p>
          ) : null}
        </div>
      )}

      {items.length === 0 ? (
        <p className="mt-4 text-sm text-[var(--text-muted)]">{t("empty")}</p>
      ) : (
        <ul className="mt-4 flex flex-wrap gap-2">
          {items.map((item) => (
            <li key={item.id}>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] py-1 pl-3 pr-1.5 text-sm backdrop-blur-sm">
                <button
                  type="button"
                  onClick={() => setEditing(item)}
                  className="font-medium text-[var(--text-primary)] outline-none hover:text-[var(--brand-primary)] focus-visible:text-[var(--brand-primary)] focus-visible:underline"
                  aria-label={t("editAria", { name: item.name ?? "" })}
                >
                  {item.name}
                  {item.category_label ? (
                    <span className="ml-1 text-xs font-normal text-[var(--text-muted)]">
                      · {item.category_label}
                    </span>
                  ) : null}
                </button>
                <button
                  type="button"
                  onClick={() => setToDelete(item)}
                  aria-label={t("removeAria", { name: item.name ?? "" })}
                  className="rounded-full p-1 text-[var(--text-muted)] outline-none transition-colors hover:bg-[var(--red-50)] hover:text-[var(--brand-red)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
                >
                  <X aria-hidden weight="bold" className="size-3.5" />
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}

      <SkillEditModal
        open={editing !== null}
        onClose={() => setEditing(null)}
        item={editing}
      />
      <ConfirmDeleteModal
        open={toDelete !== null}
        onClose={() => setToDelete(null)}
        onConfirm={() => toDelete && del.mutate(toDelete.id)}
        title={t("deleteTitle")}
        description={t("deleteBody")}
        loading={del.isPending}
      />
    </section>
  );
}
