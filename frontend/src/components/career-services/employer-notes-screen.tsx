"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Buildings, PencilSimple, PlusCircle } from "@phosphor-icons/react";
import {
  Button,
  EmptyState,
  Modal,
  Select,
  SkeletonCard,
  StatusBadge,
  Textarea,
  useToast,
} from "@/components/ui";
import { CareerServicesShell } from "./career-services-shell";
import { CareerServicesPermissionGate } from "./permission-gate";
import { EmployerPicker } from "./employer-picker";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import {
  ApiError,
  NOTE_CATEGORIES,
  NOTE_VISIBILITIES,
  careerServicesApi,
  type EmployerRelationshipNote,
  type NoteCategory,
  type NoteVisibility,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

const CATEGORY_TONE: Record<NoteCategory, "info" | "active" | "pending" | "accepted" | "rejected"> = {
  general: "info",
  partnership: "active",
  hiring_event: "accepted",
  feedback: "pending",
  escalation: "rejected",
};

export function EmployerNotesScreen() {
  const t = useTranslations("careerServices");
  const locale = useLocale();
  const toast = useToast();
  const getErrorMessage = useApiErrorMessage();
  const qc = useQueryClient();

  const [employerFilter, setEmployerFilter] = useState<{ id: string; label: string } | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [employer, setEmployer] = useState<{ id: string; label: string } | null>(null);
  const [category, setCategory] = useState<NoteCategory>("general");
  const [visibility, setVisibility] = useState<NoteVisibility>("all_staff");
  const [noteText, setNoteText] = useState("");

  const [editTarget, setEditTarget] = useState<EmployerRelationshipNote | null>(null);
  const [editText, setEditText] = useState("");

  const query = useQuery({
    queryKey: ["career-services", "employer-notes", locale, employerFilter?.id],
    queryFn: () => careerServicesApi.listEmployerNotes(locale, employerFilter?.id),
    retry: false,
  });

  const refresh = () =>
    qc.invalidateQueries({ queryKey: ["career-services", "employer-notes"] });

  const closeCreate = () => {
    setCreateOpen(false);
    setEmployer(null);
    setNoteText("");
  };

  const create = useMutation({
    mutationFn: () =>
      careerServicesApi.createEmployerNote(
        {
          employer_org_id: employer!.id,
          category,
          visibility,
          note_text: noteText.trim(),
        },
        locale,
      ),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("employerNotes.createdToast") });
      closeCreate();
      refresh();
    },
    onError: (error) => toast.show({ tone: "error", title: getErrorMessage(error) }),
  });

  const update = useMutation({
    mutationFn: () =>
      careerServicesApi.updateEmployerNote(editTarget!.id, { note_text: editText.trim() }, locale),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("employerNotes.updatedToast") });
      setEditTarget(null);
      refresh();
    },
    onError: (error) => toast.show({ tone: "error", title: getErrorMessage(error) }),
  });

  const notes = useMemo(() => query.data ?? [], [query.data]);
  const permissionState =
    query.isError && query.error instanceof ApiError ? (
      <CareerServicesPermissionGate error={query.error} bodyOverride={t("employerNotes.permissionBody")} />
    ) : null;

  return (
    <CareerServicesShell
      title={t("employerNotes.title")}
      description={t("employerNotes.subtitle")}
      actions={
        !permissionState && (
          <Button onClick={() => setCreateOpen(true)}>
            <PlusCircle aria-hidden weight="bold" className="size-4" />
            {t("employerNotes.addNote")}
          </Button>
        )
      }
    >
      {permissionState ?? (
        <>
          <div className="mb-4 max-w-sm">
            <EmployerPicker value={employerFilter} onChange={setEmployerFilter} />
          </div>

          {query.isLoading ? (
            <div className="grid gap-4 md:grid-cols-2">
              <SkeletonCard />
              <SkeletonCard />
            </div>
          ) : query.isError ? (
            <EmptyState
              kind="error"
              title={t("employerNotes.loadFailed")}
              description={getErrorMessage(query.error)}
            />
          ) : notes.length === 0 ? (
            <EmptyState
              kind="empty"
              icon={Buildings}
              title={t("employerNotes.emptyTitle")}
              description={t("employerNotes.emptyBody")}
              action={
                <Button onClick={() => setCreateOpen(true)}>
                  <PlusCircle aria-hidden weight="bold" className="size-4" />
                  {t("employerNotes.addNote")}
                </Button>
              }
            />
          ) : (
            <div className="space-y-3">
              {notes.map((note) => (
                <article
                  key={note.id}
                  className="rounded-xl border border-white/70 bg-white/85 p-4 shadow-sm backdrop-blur"
                >
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge tone={CATEGORY_TONE[note.category]}>{note.category_label}</StatusBadge>
                      <span className="text-xs text-[var(--text-muted)]">{note.visibility_label}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-[var(--text-muted)]">
                        {formatDateTime(note.created_at, locale)}
                      </span>
                      <Button
                        variant="ghost"
                        size="xs"
                        onClick={() => {
                          setEditTarget(note);
                          setEditText(note.note_text);
                        }}
                      >
                        <PencilSimple aria-hidden weight="bold" className="size-4" />
                        {t("employerNotes.edit")}
                      </Button>
                    </div>
                  </div>
                  <p className="whitespace-pre-wrap text-sm text-[var(--text-primary)]">{note.note_text}</p>
                </article>
              ))}
            </div>
          )}
        </>
      )}

      <Modal
        open={createOpen}
        onClose={closeCreate}
        title={t("employerNotes.createTitle")}
        size="md"
        footer={
          <>
            <Button variant="ghost" onClick={closeCreate} disabled={create.isPending}>
              {t("cancel")}
            </Button>
            <Button
              loading={create.isPending}
              disabled={!employer || !noteText.trim()}
              onClick={() => create.mutate()}
            >
              {t("save")}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <EmployerPicker value={employer} onChange={setEmployer} required />
          <div className="grid gap-4 sm:grid-cols-2">
            <Select
              label={t("employerNotes.categoryLabel")}
              value={category}
              onChange={(e) => setCategory(e.target.value as NoteCategory)}
              options={NOTE_CATEGORIES.map((c) => ({ value: c, label: t(`noteCategory.${c}`) }))}
            />
            <Select
              label={t("employerNotes.visibilityLabel")}
              value={visibility}
              onChange={(e) => setVisibility(e.target.value as NoteVisibility)}
              options={NOTE_VISIBILITIES.map((v) => ({ value: v, label: t(`noteVisibility.${v}`) }))}
            />
          </div>
          <Textarea
            label={t("employerNotes.noteTextLabel")}
            required
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
            rows={4}
          />
        </div>
      </Modal>

      <Modal
        open={!!editTarget}
        onClose={() => setEditTarget(null)}
        title={t("employerNotes.editTitle")}
        size="md"
        footer={
          <>
            <Button variant="ghost" onClick={() => setEditTarget(null)} disabled={update.isPending}>
              {t("cancel")}
            </Button>
            <Button loading={update.isPending} disabled={!editText.trim()} onClick={() => update.mutate()}>
              {t("save")}
            </Button>
          </>
        }
      >
        <Textarea
          label={t("employerNotes.noteTextLabel")}
          required
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
          rows={4}
        />
      </Modal>
    </CareerServicesShell>
  );
}
