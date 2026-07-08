"use client";

import { useId, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { Button, Modal, useToast } from "@/components/ui";
import { ApiError, applicationsApi, type Interview } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { MemberMultiSelect } from "./member-multi-select";

export function AssigneesModal({
  applicationId,
  interview,
  onClose,
  onSuccess,
}: {
  applicationId: string;
  interview: Interview;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const t = useTranslations("interviews");
  const tc = useTranslations("common");
  const toast = useToast();
  const apiError = useApiErrorMessage();
  const fieldId = useId();
  const [selected, setSelected] = useState<string[]>(
    interview.assignees.map((a) => a.user_id),
  );

  const save = useMutation({
    mutationFn: () =>
      applicationsApi.setInterviewAssignees(
        applicationId,
        interview.id,
        selected,
      ),
    onSuccess,
    onError: (e) => {
      if (e instanceof ApiError && e.isValidation) {
        toast.show({ tone: "error", title: t("assigneeInvalidToast") });
        return;
      }
      toast.show({ tone: "error", title: apiError(e) });
    },
  });

  return (
    <Modal
      open
      onClose={save.isPending ? () => {} : onClose}
      title={t("assigneesTitle")}
      description={t("assigneesDescription")}
      size="sm"
      closeLabel={tc("close")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={save.isPending}>
            {tc("cancel")}
          </Button>
          <Button
            variant="primary"
            loading={save.isPending}
            onClick={() => save.mutate()}
          >
            {t("assigneesSubmit")}
          </Button>
        </>
      }
    >
      <MemberMultiSelect
        idBase={fieldId}
        selected={selected}
        onChange={setSelected}
      />
    </Modal>
  );
}
