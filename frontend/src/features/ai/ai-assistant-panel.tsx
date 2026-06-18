"use client";

import { AIOperations } from "./ai-operations";
import { useI18n } from "@/lib/i18n/provider";
import { SidePanel } from "@/components/ui/side-panel";

export function AIAssistantPanel({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { dictionary } = useI18n();
  return (
    <SidePanel
      open={open}
      onOpenChange={onOpenChange}
      title={dictionary.shell.aiAssistant}
      description={dictionary.ai.description}
      width="max-w-2xl"
    >
      <AIOperations compact />
    </SidePanel>
  );
}
