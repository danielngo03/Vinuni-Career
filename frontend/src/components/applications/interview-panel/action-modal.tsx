"use client";

import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { Button, Modal } from "@/components/ui";
import { ApiError } from "@/lib/api";

/** Generic confirm-action modal (cancel / other single-step mutations). */
export function ActionModal({
  open,
  title,
  description,
  confirmLabel,
  tone,
  loadingFn,
  version,
  onClose,
  onSuccess,
  onConflict,
  onError,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  tone: "primary" | "danger";
  loadingFn: (version?: number) => Promise<unknown>;
  version?: number;
  onClose: () => void;
  onSuccess: () => void;
  onConflict: () => void;
  onError: (e: unknown) => void;
}) {
  const tc = useTranslations("common");
  const run = useMutation({
    mutationFn: () => loadingFn(version),
    onSuccess,
    onError: (e) => {
      if (e instanceof ApiError && e.isConflict) return onConflict();
      onError(e);
    },
  });

  return (
    <Modal
      open={open}
      onClose={run.isPending ? () => {} : onClose}
      title={title}
      description={description}
      size="sm"
      closeLabel={tc("close")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={run.isPending}>
            {tc("cancel")}
          </Button>
          <Button variant={tone} loading={run.isPending} onClick={() => run.mutate()}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <p className="type-small text-muted-foreground">{description}</p>
    </Modal>
  );
}
