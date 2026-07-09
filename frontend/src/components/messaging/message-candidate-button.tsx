"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { MessageSquareText } from "lucide-react";
import { Button, useToast } from "@/components/ui";
import {
  ApiError,
  messagingApi,
  type ThreadSummary,
} from "@/lib/api";
import { MessagingCenter } from "./messaging-center";

export interface MessageCandidateButtonProps {
  /** The application that binds this partner↔candidate thread. */
  applicationId: string;
  size?: "sm" | "md";
}

/**
 * Partner-side initiation, enforced in the UI (backend re-checks): creates (or
 * re-opens — the server is idempotent per application/org) the application-bound
 * candidate thread and opens it in the messaging center. The recipient is
 * resolved SERVER-SIDE from the application context, so the partner never needs
 * (or sees) the student's user id — this works even while the applicant is
 * anonymous. The counterpart label is rendered by the server (an anonymous
 * handle until reveal); this component never sends or displays the student's
 * name/email.
 */
export function MessageCandidateButton({
  applicationId,
  size = "sm",
}: MessageCandidateButtonProps) {
  const t = useTranslations("messaging");
  const { show } = useToast();
  const [thread, setThread] = useState<ThreadSummary | null>(null);
  const [open, setOpen] = useState(false);

  const create = useMutation({
    mutationFn: () =>
      messagingApi.createThread({
        kind: "direct",
        context_type: "application",
        context_id: applicationId,
        // Recipient resolved server-side from the application; partners never
        // pass the (possibly anonymous) student's user id.
        recipient_ids: [],
      }),
    onSuccess: (data) => {
      setThread(data);
      setOpen(true);
    },
    onError: (err) => {
      const msg =
        err instanceof ApiError
          ? err.isNotFound
            ? t("errors.candidateUnavailable")
            : err.message
          : t("errors.candidateUnavailable");
      show({ tone: "error", title: msg });
    },
  });

  return (
    <>
      <Button
        variant="secondary"
        size={size}
        loading={create.isPending}
        disabled={create.isPending}
        onClick={() => create.mutate()}
      >
        <MessageSquareText aria-hidden strokeWidth={1.8} className="size-4" />
        {t("messageCandidate")}
      </Button>

      <MessagingCenter
        open={open}
        onClose={() => setOpen(false)}
        initialThread={thread}
      />
    </>
  );
}
