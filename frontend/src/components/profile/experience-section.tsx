"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { Briefcase } from "@phosphor-icons/react";
import { profileApi, type ExperienceItem } from "@/lib/api";
import { formatMonthYear } from "@/lib/format";
import { ExperienceFormModal } from "./experience-form-modal";
import { ConfirmDeleteModal } from "./confirm-delete-modal";
import { EmptyHint, RowActions, SectionShell } from "./section-shell";
import { useProfileMutations } from "./use-profile-mutations";

function dateRange(
  item: ExperienceItem,
  locale: string,
  current: string,
): string {
  const start = formatMonthYear(item.start_date, locale);
  const end = item.is_current
    ? current
    : formatMonthYear(item.end_date, locale);
  if (!start && !end) return "";
  return [start, end].filter(Boolean).join(" – ");
}

export function ExperienceSection({ items }: { items: ExperienceItem[] }) {
  const t = useTranslations("profile.experience");
  const tc = useTranslations("common");
  const locale = useLocale();
  const { reloadProfile, handleError } = useProfileMutations();

  const [editing, setEditing] = useState<ExperienceItem | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [toDelete, setToDelete] = useState<ExperienceItem | null>(null);

  const del = useMutation({
    mutationFn: (id: string) => profileApi.deleteChild("experience", id),
    onSuccess: () => {
      reloadProfile();
      setToDelete(null);
    },
    onError: (e) => {
      handleError(e);
      setToDelete(null);
    },
  });

  const openAdd = () => {
    setEditing(null);
    setFormOpen(true);
  };
  const openEdit = (item: ExperienceItem) => {
    setEditing(item);
    setFormOpen(true);
  };

  return (
    <SectionShell
      title={t("title")}
      description={t("intro")}
      icon={Briefcase}
      iconGradient="icon-chip-success"
      addLabel={t("add")}
      onAdd={openAdd}
    >
      {items.length === 0 ? (
        <EmptyHint>{t("empty")}</EmptyHint>
      ) : (
        <ul className="space-y-3">
          {items.map((item) => (
            <li
              key={item.id}
              className="flex items-start justify-between gap-3 rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] p-4 backdrop-blur-sm"
            >
              <div className="min-w-0">
                <p className="font-semibold text-[var(--text-primary)]">
                  {item.title}
                  {item.company_name ? (
                    <span className="font-normal text-[var(--text-secondary)]">
                      {" "}
                      · {item.company_name}
                    </span>
                  ) : null}
                </p>
                <p className="mt-0.5 text-xs text-[var(--text-muted)]">
                  {[
                    item.employment_type_label,
                    item.location,
                    dateRange(item, locale, tc("present")),
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
                {item.skills_used.length > 0 && (
                  <p className="mt-1 text-xs text-[var(--text-secondary)]">
                    {item.skills_used.join(", ")}
                  </p>
                )}
                {item.description && (
                  <p className="mt-1.5 whitespace-pre-line text-sm text-[var(--text-secondary)]">
                    {item.description}
                  </p>
                )}
              </div>
              <RowActions
                editLabel={tc("edit")}
                deleteLabel={tc("delete")}
                onEdit={() => openEdit(item)}
                onDelete={() => setToDelete(item)}
              />
            </li>
          ))}
        </ul>
      )}

      <ExperienceFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
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
    </SectionShell>
  );
}
