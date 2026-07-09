"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Megaphone, Send } from "lucide-react";
import { Button, Input, Modal, Textarea, useToast } from "@/components/ui";
import { MessagingScreen } from "./messaging-screen";
import { messagingApi } from "@/lib/api";
import { MESSAGING_THREADS_KEY } from "./query-keys";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

/**
 * University messaging workspace. Extends the shared MessagingScreen with a
 * "New announcement" CTA — university staff can broadcast one-way messages to
 * all students (kind="announcement"). The inbox, thread detail, and read/mute
 * controls are inherited from MessagingScreen.
 */
export function UniversityMessagesScreen() {
  const t = useTranslations("messaging");
  const [composeOpen, setComposeOpen] = useState(false);

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex items-center justify-between">
        <div />
        <Button
          variant="primary"
          size="sm"
          onClick={() => setComposeOpen(true)}
        >
          <Megaphone aria-hidden strokeWidth={1.9} className="size-4" />
          {t("newAnnouncement")}
        </Button>
      </div>

      <div className="flex-1">
        <MessagingScreen persona="university" />
      </div>

      <AnnounceModal
        open={composeOpen}
        onClose={() => setComposeOpen(false)}
      />
    </div>
  );
}

/* ── Announcement compose modal ────────────────────────────────────────────── */

function AnnounceModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const t = useTranslations("messaging");
  const tc = useTranslations("common");
  const toast = useToast();
  const apiError = useApiErrorMessage();
  const qc = useQueryClient();

  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const BODY_MAX = 4000;

  const mutation = useMutation({
    mutationFn: () =>
      messagingApi.createThread({
        kind: "announcement",
        subject: subject.trim() || null,
        first_message: body.trim(),
        recipient_ids: [],
      }),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("announcementSent") });
      void qc.invalidateQueries({ queryKey: MESSAGING_THREADS_KEY });
      setSubject("");
      setBody("");
      onClose();
    },
    onError: (e) => {
      toast.show({ tone: "error", title: apiError(e) });
    },
  });

  const bodyEmpty = body.trim().length === 0;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t("newAnnouncement")}
      description={t("announcementHint")}
      closeLabel={tc("close")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={mutation.isPending}>
            {tc("cancel")}
          </Button>
          <Button
            variant="primary"
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
            disabled={bodyEmpty}
          >
            <Send aria-hidden strokeWidth={2} className="size-4" />
            {t("send")}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input
          label={t("announceSubjectLabel")}
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          placeholder={t("announceSubjectPlaceholder")}
        />
        <div>
          <Textarea
            label={t("announceBodyLabel")}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder={t("announceBodyPlaceholder")}
            rows={6}
            maxLength={BODY_MAX}
            required
          />
          <p aria-hidden className="mt-1 text-right text-xs text-[var(--text-muted)]">
            {body.length}/{BODY_MAX}
          </p>
        </div>
      </div>
    </Modal>
  );
}
