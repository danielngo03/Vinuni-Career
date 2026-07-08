"use client";

import { useTranslations } from "next-intl";
import {
  Button,
  Modal,
  Select,
  Textarea,
  type SelectOption,
} from "@/components/ui";
import type { PipelineStage } from "@/lib/api";

export function RollbackModal({
  open,
  handle,
  stages,
  stageId,
  onStageChange,
  reason,
  onReasonChange,
  fieldError,
  minReason,
  loading,
  onClose,
  onSubmit,
}: {
  open: boolean;
  handle: string;
  stages: PipelineStage[];
  stageId: string;
  onStageChange: (v: string) => void;
  reason: string;
  onReasonChange: (v: string) => void;
  fieldError: string | null;
  minReason: number;
  loading: boolean;
  onClose: () => void;
  onSubmit: () => void;
}) {
  const t = useTranslations("pipeline");
  const tc = useTranslations("common");
  const reasonLen = reason.trim().length;
  const reasonValid = reasonLen >= minReason;
  const noPriorStages = stages.length === 0;

  const options: SelectOption[] = [
    { value: "", label: t("targetPlaceholder") },
    ...stages.map((s) => ({ value: s.id, label: s.name })),
  ];

  return (
    <Modal
      open={open}
      onClose={loading ? () => {} : onClose}
      title={t("rollbackTitle")}
      description={t("rollbackDescription", { handle })}
      size="sm"
      closeLabel={tc("close")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            {tc("cancel")}
          </Button>
          <Button
            variant="primary"
            loading={loading}
            disabled={loading || noPriorStages || !stageId || !reasonValid}
            onClick={onSubmit}
          >
            {t("rollbackSubmit")}
          </Button>
        </>
      }
    >
      {noPriorStages ? (
        <p className="text-sm text-[var(--text-secondary)]">
          {t("noPriorStages")}
        </p>
      ) : (
        <div className="space-y-4">
          <Select
            label={t("targetLabel")}
            required
            options={options}
            value={stageId}
            error={fieldError && !stageId ? fieldError : undefined}
            onChange={(e) => onStageChange(e.target.value)}
          />
          <div>
            <Textarea
              label={t("reasonLabel")}
              required
              rows={4}
              maxLength={500}
              value={reason}
              placeholder={t("reasonPlaceholder")}
              error={fieldError && stageId ? fieldError : undefined}
              onChange={(e) => onReasonChange(e.target.value)}
            />
            <p
              className={
                reasonValid
                  ? "mt-1 text-xs text-[var(--text-muted)]"
                  : "mt-1 text-xs text-[var(--text-secondary)]"
              }
            >
              {t("reasonHelp", { min: minReason, count: reasonLen })}
            </p>
          </div>
        </div>
      )}
    </Modal>
  );
}
