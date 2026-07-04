"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { GraduationCap } from "@phosphor-icons/react";
import { profileApi, type EducationItem } from "@/lib/api";
import { formatMonthYear } from "@/lib/format";
import { EducationFormModal } from "./education-form-modal";
import { ConfirmDeleteModal } from "./confirm-delete-modal";
import { EmptyHint, RowActions, SectionShell } from "./section-shell";
import { useProfileMutations } from "./use-profile-mutations";

function dateRange(
  item: EducationItem,
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

export function EducationSection({ items }: { items: EducationItem[] }) {
  const t = useTranslations("profile.education");
  const tc = useTranslations("common");
  const locale = useLocale();
  const { reloadProfile, handleError } = useProfileMutations();

  const [editing, setEditing] = useState<EducationItem | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [toDelete, setToDelete] = useState<EducationItem | null>(null);

  const del = useMutation({
    mutationFn: (id: string) => profileApi.deleteChild("education", id),
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
  const openEdit = (item: EducationItem) => {
    setEditing(item);
    setFormOpen(true);
  };

  return (
    <SectionShell
      title={t("title")}
      description={t("intro")}
      icon={GraduationCap}
      iconGradient="icon-chip-primary"
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
                  {item.institution}
                </p>
                <p className="text-sm text-[var(--text-secondary)]">
                  {[item.degree, item.field_of_study]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
                {dateRange(item, locale, tc("present")) && (
                  <p className="mt-0.5 text-xs text-[var(--text-muted)]">
                    {dateRange(item, locale, tc("present"))}
                    {item.gpa != null ? ` · ${t("gpa")}: ${item.gpa}` : ""}
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

      <EducationFormModal
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
