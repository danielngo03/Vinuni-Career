"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { PaperPlaneTilt, Megaphone } from "@phosphor-icons/react";
import { Button, Input, Modal, Textarea, useToast } from "@/components/ui";
import { OrgInboxScreen } from "./org-inbox-screen";
import { messagingApi } from "@/lib/api";
import { MESSAGING_THREADS_KEY, MESSAGING_INBOX_ROOT } from "./query-keys";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

/**
 * University messaging workspace = the org shared inbox (team triage, assign,
 * resolve, request-gate handling) PLUS a "New announcement" CTA that broadcasts a
 * one-way message to all students (kind="announcement"). University staff are
 * moderators, so they can read + moderate any thread routed to their inbox.
 */
export function UniversityMessagesScreen() {
  const t = useTranslations("messaging");
  const [composeOpen, setComposeOpen] = useState(false);

  return (
    <>
      <OrgInboxScreen
        persona="university"
        headerExtra={
          <Button
            variant="secondary"
            size="xs"
            onClick={() => setComposeOpen(true)}
          >
            <Megaphone aria-hidden weight="duotone" className="size-3.5" />
            {t("newAnnouncement")}
          </Button>
        }
      />
      <AnnounceModal open={composeOpen} onClose={() => setComposeOpen(false)} />
    </>
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
      void qc.invalidateQueries({ queryKey: MESSAGING_INBOX_ROOT });
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
            <PaperPlaneTilt aria-hidden weight="duotone" className="size-4" />
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
