"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Pencil, Plus } from "lucide-react";
import { Button, Modal, Select, Textarea, useToast } from "@/components/ui";
import { Card, EmptyState, StatusChip, type ChipTone } from "@/components/kit";
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

const CATEGORY_TONE: Record<NoteCategory, ChipTone> = {
  general: "neutral",
  partnership: "indigo",
  hiring_event: "teal",
  feedback: "amber",
  escalation: "danger",
};

export function EmployerNotesScreen() {
  const t = useTranslations("careerServices");
  const locale = useLocale();
  const toast = useToast();
  const getErrorMessage = useApiErrorMessage();
  const qc = useQueryClient();

  const [employerFilter, setEmployerFilter] = React.useState<{ id: string; label: string } | null>(null);
  const [createOpen, setCreateOpen] = React.useState(false);
  const [employer, setEmployer] = React.useState<{ id: string; label: string } | null>(null);
  const [category, setCategory] = React.useState<NoteCategory>("general");
  const [visibility, setVisibility] = React.useState<NoteVisibility>("all_staff");
  const [noteText, setNoteText] = React.useState("");

  const [editTarget, setEditTarget] = React.useState<EmployerRelationshipNote | null>(null);
  const [editText, setEditText] = React.useState("");

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

  const notes = query.data ?? [];
  const permissionState =
    query.isError && query.error instanceof ApiError ? (
      <CareerServicesPermissionGate error={query.error} bodyOverride={t("employerNotes.permissionBody")} />
    ) : null;

  const addButton = (
    <Button onClick={() => setCreateOpen(true)} size="sm">
      <Plus className="size-4" strokeWidth={2} />
      {t("employerNotes.addNote")}
    </Button>
  );

  return (
    <CareerServicesShell
      title={t("employerNotes.title")}
      description={t("employerNotes.subtitle")}
      actions={!permissionState ? addButton : undefined}
    >
      {permissionState ?? (
        <div className="space-y-4">
          <div className="max-w-sm">
            <EmployerPicker value={employerFilter} onChange={setEmployerFilter} />
          </div>

          {query.isPending ? (
            <div className="space-y-3">
              <div className="h-24 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
              <div className="h-24 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
            </div>
          ) : query.isError ? (
            <EmptyState kind="error" title={t("employerNotes.loadFailed")} description={getErrorMessage(query.error)} />
          ) : notes.length === 0 ? (
            <EmptyState
              kind="empty"
              icon={Building2}
              title={t("employerNotes.emptyTitle")}
              description={t("employerNotes.emptyBody")}
              action={addButton}
            />
          ) : (
            <div className="space-y-3">
              {notes.map((note) => (
                <Card key={note.id} padded>
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusChip tone={CATEGORY_TONE[note.category]} dot>
                        {note.category_label}
                      </StatusChip>
                      <span className="type-caption text-muted-foreground">{note.visibility_label}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="type-caption tabular-nums text-muted-foreground">
                        {formatDateTime(note.created_at, locale)}
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setEditTarget(note);
                          setEditText(note.note_text);
                        }}
                      >
                        <Pencil className="size-4" strokeWidth={1.8} />
                        {t("employerNotes.edit")}
                      </Button>
                    </div>
                  </div>
                  <p className="whitespace-pre-wrap text-sm text-foreground">{note.note_text}</p>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Add note */}
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

      {/* Edit note */}
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
