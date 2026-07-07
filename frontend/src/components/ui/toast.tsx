"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
import { useTranslations } from "next-intl";
import {
  CheckCircle,
  Info,
  Warning,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

type ToastTone = "success" | "error" | "warning" | "info";

interface Toast {
  id: string;
  tone: ToastTone;
  title: string;
  description?: string;
}

interface ToastContextValue {
  show: (toast: Omit<Toast, "id">) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const TONE_ICON = {
  success: CheckCircle,
  error: WarningCircle,
  warning: Warning,
  info: Info,
} as const;

const TONE_STYLE: Record<ToastTone, string> = {
  success: "text-[var(--color-success)]",
  error: "text-[var(--brand-red)]",
  warning: "text-[var(--color-warning)]",
  info: "text-[var(--color-info)]",
};

/** App-wide toast host. Replaces alert(); announces via aria-live. */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const tc = useTranslations("common");
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const show = useCallback(
    (toast: Omit<Toast, "id">) => {
      const id = Math.random().toString(36).slice(2);
      setToasts((prev) => [...prev, { ...toast, id }]);
      window.setTimeout(() => dismiss(id), 5000);
    },
    [dismiss],
  );

  const value = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-[60] flex flex-col items-center gap-2 p-4 sm:items-end"
      >
        {toasts.map((toast) => {
          const Icon = TONE_ICON[toast.tone];
          return (
            <div
              key={toast.id}
              role="status"
              className="pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4 shadow-[var(--shadow-lg)]"
            >
              <Icon
                aria-hidden
                weight="duotone"
                className={cn("mt-0.5 size-5 shrink-0", TONE_STYLE[toast.tone])}
              />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  {toast.title}
                </p>
                {toast.description && (
                  <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
                    {toast.description}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={() => dismiss(toast.id)}
                aria-label={tc("close")}
                className="rounded-md p-1 text-[var(--text-muted)] outline-none hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)]"
              >
                <X aria-hidden weight="bold" className="size-4" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
