"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Sparkles } from "lucide-react";
import { AiChatWindow } from "@/components/ai-assistant/ai-chat-window";
import { cn } from "@/lib/utils";

/**
 * Header entry to the VinUni AI assistant, replacing the floating rail's AI
 * button. Icon-only trigger (matching the notification/messaging bells) that
 * toggles the shared `AiChatWindow`. It gets the only colored treatment in the
 * student header so the assistant reads as a special, high-signal action
 * without relying on motion.
 */
export function HeaderAiButton() {
  const tNav = useTranslations("nav");
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        aria-label={tNav("aiAssistant")}
        aria-haspopup="dialog"
        aria-expanded={open}
        title={tNav("aiAssistant")}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "relative inline-flex size-9 items-center justify-center rounded-lg border outline-none transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-[var(--ai-accent)]/50",
          open
            ? "border-[var(--ai-accent)] bg-[var(--ai-accent)] text-white shadow-[var(--shadow-teal)] hover:bg-[var(--ai-accent-strong)]"
            : "border-[var(--ai-accent-ring)] bg-[var(--ai-accent-surface)] text-[var(--ai-accent-strong)] shadow-[var(--ai-chip-shadow)] hover:border-[var(--ai-accent)] hover:bg-[var(--ai-accent-surface-hover)]",
        )}
      >
        <Sparkles
          aria-hidden
          strokeWidth={1.8}
          className={cn("size-5", open ? "text-white" : "text-[var(--ai-accent-strong)]")}
        />
      </button>

      <AiChatWindow open={open} onClose={() => setOpen(false)} variant="roomy" />
    </>
  );
}
