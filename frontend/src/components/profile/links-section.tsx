"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { LinkSimple } from "@phosphor-icons/react";
import { profileApi, type LinkItem } from "@/lib/api";
import { LinkFormModal } from "./link-form-modal";
import { ConfirmDeleteModal } from "./confirm-delete-modal";
import { EmptyHint, RowActions, SectionShell } from "./section-shell";
import { useProfileMutations } from "./use-profile-mutations";

export function LinksSection({ items }: { items: LinkItem[] }) {
  const t = useTranslations("profile.links");
  const tc = useTranslations("common");
  const { reloadProfile, handleError } = useProfileMutations();

  const [editing, setEditing] = useState<LinkItem | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [toDelete, setToDelete] = useState<LinkItem | null>(null);

  const del = useMutation({
    mutationFn: (id: string) => profileApi.deleteChild("links", id),
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
  const openEdit = (item: LinkItem) => {
    setEditing(item);
    setFormOpen(true);
  };

  return (
    <SectionShell
      title={t("title")}
      description={t("intro")}
      icon={LinkSimple}
      iconGradient="icon-chip-success"
      addLabel={t("add")}
      onAdd={openAdd}
    >
      {items.length === 0 ? (
        <EmptyHint>{t("empty")}</EmptyHint>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li
              key={item.id}
              className="flex items-center justify-between gap-3 rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] p-3 backdrop-blur-sm"
            >
              <div className="flex min-w-0 items-center gap-2">
                <LinkSimple
                  aria-hidden
                  weight="duotone"
                  className="size-4 shrink-0 text-[var(--teal-600)]"
                />
                <div className="min-w-0">
                  <p className="truncate font-medium text-[var(--text-primary)]">
                    {item.label || item.url}
                  </p>
                  <a
                    href={item.url ?? "#"}
                    target="_blank"
                    rel="noopener noreferrer nofollow"
                    className="truncate text-xs text-[var(--brand-primary)] underline-offset-2 outline-none hover:underline focus-visible:underline"
                  >
                    {item.url}
                  </a>
                </div>
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

      <LinkFormModal
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
