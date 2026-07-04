"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import {
  Heart,
  ChatCircleText,
  Sparkle,
  Plus,
  X,
  EnvelopeSimple,
  ChatCenteredDots,
} from "@phosphor-icons/react";
import { useRouter } from "@/i18n/navigation";
import { useAuthStore } from "@/stores/auth-store";
import { useUiStore } from "@/stores/ui-store";
import { MessagingCenter } from "@/components/messaging/messaging-center";
import { AiChatWindow } from "@/components/ai-assistant/ai-chat-window";
import { FeedbackModal } from "./feedback-modal";
import { cn } from "@/lib/utils";

const SAVED_ROUTE = "/student/saved";
const INVITATIONS_ROUTE = "/student/invitations";

/**
 * Bottom-right floating quick-action rail for the public + student marketplace
 * surfaces (spec §3). It is a navigation affordance, not decoration:
 *
 *  - Saved jobs (`Heart`): guests open the intent-preserving login modal;
 *    authenticated users go to their saved list (honest under-construction).
 *  - Messages (`ChatCircleText`): authenticated only — opens the existing
 *    MessagingCenter. Hidden for guests.
 *  - VinUni AI assistant (`Sparkle`): honest-disabled "Sắp ra mắt".
 *
 * Desktop renders the expanded vertical rail; mobile collapses into ONE compact
 * launcher (FAB) that expands into the same actions. The container is
 * pointer-events-none with pointer-events-auto controls so it never blocks
 * content, and it sits above the safe-area so it never overlaps sticky apply
 * bars, the chat composer, footer, cookie notes, or the mobile nav.
 */
export function FloatingActionRail() {
  const tNav = useTranslations("nav");
  const tMsg = useTranslations("messaging");
  const tRail = useTranslations("rail");
  const router = useRouter();
  const authed = useAuthStore((s) => s.status === "authenticated");
  const persona = useAuthStore((s) => s.user?.persona);
  const openLoginModal = useUiStore((s) => s.openLoginModal);
  const showStudentActions = !authed || persona === "student";

  const [msgOpen, setMsgOpen] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);

  function handleSaved() {
    setExpanded(false);
    if (authed) {
      router.push(SAVED_ROUTE);
      return;
    }
    openLoginModal({ label: tRail("savedIntent"), returnTo: SAVED_ROUTE });
  }

  function handleInvitations() {
    setExpanded(false);
    if (authed) {
      router.push(INVITATIONS_ROUTE);
      return;
    }
    openLoginModal({ label: tRail("invitationsHint"), returnTo: INVITATIONS_ROUTE });
  }

  function handleMessages() {
    setExpanded(false);
    setMsgOpen(true);
  }

  function handleAi() {
    setExpanded(false);
    setAiOpen((v) => !v);
  }

  // Build the action set for the current persona (hide unavailable actions).
  // Spec order: saved → invitations → messages → feedback → AI
  const actions: RailAction[] = [
    ...(showStudentActions
      ? [
          {
            key: "saved",
            label: tNav("saved"),
            icon: Heart,
            onClick: handleSaved,
          },
          {
            key: "invitations",
            label: tRail("invitationsLabel"),
            icon: EnvelopeSimple,
            onClick: handleInvitations,
          },
        ]
      : []),
    ...(authed
      ? [
          {
            key: "messages",
            label: tMsg("title"),
            icon: ChatCircleText,
            onClick: handleMessages,
          } as RailAction,
        ]
      : []),
    {
      key: "feedback",
      label: tRail("feedbackLabel"),
      icon: ChatCenteredDots,
      hint: tRail("feedbackHint"),
      onClick: () => {
        setExpanded(false);
        setFeedbackOpen(true);
      },
    },
    {
      key: "ai",
      label: tNav("aiAssistant"),
      icon: Sparkle,
      onClick: handleAi,
      active: aiOpen,
    },
  ];

  return (
    <>
      <div
        className="pointer-events-none fixed bottom-0 right-0 z-40 p-4"
        style={{ paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}
      >
        {/* Desktop: persistent vertical rail. */}
        <div
          className="pointer-events-auto hidden flex-col items-end gap-3 md:flex"
          role="group"
          aria-label={tRail("title")}
        >
          {actions.map((a) => (
            <RailButton key={a.key} action={a} />
          ))}
        </div>

        {/* Mobile: one compact launcher that expands into the same actions. */}
        <div className="pointer-events-auto flex flex-col items-end gap-3 md:hidden">
          {expanded &&
            actions.map((a) => <RailButton key={a.key} action={a} labelled />)}
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            aria-label={expanded ? tRail("close") : tRail("open")}
            className="inline-flex size-14 items-center justify-center rounded-full bg-[var(--brand-primary)] text-white shadow-[var(--shadow-brand)] outline-none transition-colors hover:bg-[var(--blue-700)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40 focus-visible:ring-offset-2"
          >
            {expanded ? (
              <X aria-hidden weight="bold" className="size-6" />
            ) : (
              <Plus aria-hidden weight="bold" className="size-6" />
            )}
          </button>
        </div>
      </div>

      {authed && (
        <MessagingCenter open={msgOpen} onClose={() => setMsgOpen(false)} />
      )}
      <AiChatWindow open={aiOpen} onClose={() => setAiOpen(false)} />
      <FeedbackModal open={feedbackOpen} onClose={() => setFeedbackOpen(false)} />
    </>
  );
}

interface RailAction {
  key: string;
  label: string;
  icon: React.ElementType;
  onClick?: () => void;
  disabled?: boolean;
  hint?: string;
  active?: boolean;
}

function RailButton({
  action,
  labelled = false,
}: {
  action: RailAction;
  labelled?: boolean;
}) {
  const { key, label, icon: Icon, onClick, disabled, hint, active } = action;
  const aria = disabled && hint ? `${label} — ${hint}` : label;
  const isAi = key === "ai";
  const isPrimaryAction = key === "saved" || key === "invitations" || key === "messages";

  const button = (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={aria}
      aria-pressed={active}
      title={aria}
      className={cn(
        "inline-flex size-12 items-center justify-center rounded-full border shadow-[0_2px_12px_rgba(11,34,57,0.08)] outline-none transition-all focus-visible:ring-2 focus-visible:ring-offset-2",
        isAi
          ? active
            ? "border-[var(--ai-accent)] bg-gradient-to-br from-[var(--brand-primary)] to-[var(--ai-accent)] text-white shadow-[0_4px_16px_rgba(20,184,166,0.35)] focus-visible:ring-[var(--ai-accent)]/50"
            : "animate-ai-breathe border-[var(--ai-accent)]/40 bg-[var(--ai-accent-soft)] text-[var(--ai-accent)] focus-visible:ring-[var(--ai-accent)]/50"
          : disabled
            ? "cursor-not-allowed border-[var(--glass-border)] bg-[var(--glass-surface-light)] text-[var(--text-muted)] opacity-70 backdrop-blur-md focus-visible:ring-[var(--brand-primary)]/40"
            : isPrimaryAction
              ? "border-[var(--blue-100)] bg-[var(--surface-card)] text-[var(--brand-primary)] hover:border-[var(--brand-primary)]/55 hover:bg-[var(--blue-50)] focus-visible:ring-[var(--brand-primary)]/40"
            : "border-[var(--glass-border-strong)] bg-[var(--glass-surface)] text-[var(--brand-primary)] backdrop-blur-md hover:border-[var(--brand-primary)]/60 hover:bg-[var(--glass-surface-heavy)] focus-visible:ring-[var(--brand-primary)]/40",
      )}
    >
      <Icon aria-hidden weight={isAi ? "fill" : "duotone"} className="size-6" />
    </button>
  );

  const labelPill = (
    <span
      className={cn(
        "rounded-md px-2.5 py-1 text-xs font-semibold shadow-[var(--shadow-sm)]",
        isAi
          ? "bg-[var(--ai-accent-soft)] text-[var(--ai-accent)]"
          : "border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] text-[var(--text-secondary)] backdrop-blur-md",
      )}
    >
      {label}
      {disabled && hint ? ` · ${hint}` : ""}
    </span>
  );

  // Mobile expanded state shows the label pill always; desktop reveals it on
  // hover/focus so the rail stays compact but every action is self-describing.
  if (labelled) {
    return (
      <div className="flex items-center gap-2">
        {labelPill}
        {button}
      </div>
    );
  }

  return (
    <div className="group flex items-center gap-2">
      <span className="pointer-events-none translate-x-1 opacity-0 transition-all duration-200 group-hover:translate-x-0 group-hover:opacity-100 group-focus-within:translate-x-0 group-focus-within:opacity-100">
        {labelPill}
      </span>
      {button}
    </div>
  );
}
