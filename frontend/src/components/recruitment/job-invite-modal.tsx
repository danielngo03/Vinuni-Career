"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery, useMutation } from "@tanstack/react-query";
import { PaperPlaneTilt } from "@phosphor-icons/react";
import { Button, Modal, Select, type SelectOption, useToast } from "@/components/ui";
import { ApiError, invitationsApi, jobsApi } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onClose: () => void;
  studentId: string;
  studentName?: string;
}

export function JobInviteModal({ open, onClose, studentId, studentName }: Props) {
  const t = useTranslations("jobInvitations");
  const toast = useToast();

  const [selectedJobId, setSelectedJobId] = useState("");
  const [message, setMessage] = useState("");
  const charCount = message.length;

  useEffect(() => {
    if (open) {
      setSelectedJobId("");
      setMessage("");
    }
  }, [open]);

  const jobsQuery = useQuery({
    queryKey: ["partner-active-jobs-for-invite"],
    queryFn: () => jobsApi.listMine({ status: "active", limit: 50 }),
    enabled: open,
    staleTime: 60_000,
    retry: false,
  });

  const activeJobs = jobsQuery.data?.data ?? [];

  const jobOptions: SelectOption[] = activeJobs.map((job) => ({
    value: job.id,
    label: job.title,
  }));

  const sendMutation = useMutation({
    mutationFn: () =>
      invitationsApi.sendToStudent(selectedJobId, {
        student_id: studentId,
        message: message.trim() || undefined,
      }),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("inviteSentToast") });
      onClose();
    },
    onError: (err) => {
      const isDuplicate =
        err instanceof ApiError && err.code === "CONFLICT";
      toast.show({
        tone: "error",
        title: isDuplicate ? t("inviteErrorDuplicate") : t("inviteErrorGeneric"),
      });
    },
  });

  const canSend = !!selectedJobId && !sendMutation.isPending;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t("inviteTitle")}
      description={
        studentName
          ? `${t("inviteSubtitle")} — ${studentName}`
          : t("inviteSubtitle")
      }
    >
      <div className="space-y-4 pt-1">
        {/* Job picker */}
        <div>
          {jobsQuery.isPending ? (
            <div className="h-9 animate-pulse rounded-lg bg-white/60" />
          ) : activeJobs.length === 0 ? (
            <p className="rounded-lg border border-[var(--border-default)] bg-white/60 px-3 py-2 text-sm text-[var(--text-muted)]">
              {t("noActiveJobs")}
            </p>
          ) : (
            <Select
              label={t("selectJob")}
              value={selectedJobId}
              onChange={(e) => setSelectedJobId(e.target.value)}
              options={[{ value: "", label: `— ${t("selectJob")} —` }, ...jobOptions]}
            />
          )}
        </div>

        {/* Optional message */}
        <div>
          <label className="mb-1.5 block text-sm font-medium text-[var(--text-primary)]">
            {t("messageLabel")}
          </label>
          <div className="relative">
            <textarea
              rows={4}
              maxLength={500}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder={t("messagePlaceholder")}
              className={cn(
                "w-full resize-none rounded-xl border border-[var(--border-default)] bg-white px-4 py-3 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] ",
                "outline-none transition-colors focus:border-[var(--brand-primary)]/50 focus:ring-2 focus:ring-[var(--brand-primary)]/20",
              )}
            />
            <span
              className={cn(
                "absolute bottom-2.5 right-3 text-xs",
                charCount > 450 ? "text-[var(--warning)]" : "text-[var(--text-muted)]",
              )}
            >
              {charCount}/500
            </span>
          </div>
          <p className="mt-1 text-xs text-[var(--text-muted)]">{t("messageHint")}</p>
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>
            {t("cancelInvite")}
          </Button>
          <Button
            variant="primary"
            disabled={!canSend || activeJobs.length === 0}
            onClick={() => sendMutation.mutate()}
            className="flex items-center gap-1.5"
          >
            <PaperPlaneTilt aria-hidden weight="duotone" className="size-4" />
            {t("sendInvite")}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
