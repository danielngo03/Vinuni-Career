"use client";

import { create } from "zustand";

/**
 * Intent captured when a guest triggers an action that requires auth. After
 * login we resume this intent (CLAUDE.md: "Guest actions that need auth open
 * login modal and preserve intent").
 */
export interface AuthIntent {
  /** Human-readable action label for the modal (i18n key or text). */
  label?: string;
  /** Path to navigate to after successful auth. */
  returnTo?: string;
  /** Arbitrary payload to resume (e.g. jobId to apply to). */
  payload?: Record<string, unknown>;
}

const SIDEBAR_COLLAPSED_KEY = "vinuni:workspace-sidebar-collapsed";

/** Reads the persisted preference. Call only from a `useEffect` (post-mount)
 * so the SSR render and first client render both start from the same
 * `false` default and avoid a hydration mismatch. */
export function readPersistedSidebarCollapsed(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

interface UiState {
  // Login modal (intent-preserving)
  loginModalOpen: boolean;
  authIntent: AuthIntent | null;
  openLoginModal: (intent?: AuthIntent) => void;
  closeLoginModal: () => void;

  // Mobile sidebar drawer
  mobileNavOpen: boolean;
  setMobileNavOpen: (open: boolean) => void;

  // Desktop workspace sidebar (partner/university ops shell) — icon-only
  // collapsed rail vs full 256px sidebar. Persisted across sessions. Always
  // starts `false` (SSR-safe); WorkspaceShell syncs the real value from
  // localStorage in a post-mount effect via `setSidebarCollapsed`.
  sidebarCollapsed: boolean;
  toggleSidebarCollapsed: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
}

function persistSidebarCollapsed(value: boolean) {
  try {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, value ? "1" : "0");
  } catch {
    // localStorage unavailable (private mode / SSR edge) — in-memory state still works.
  }
}

export const useUiStore = create<UiState>((set, get) => ({
  loginModalOpen: false,
  authIntent: null,
  openLoginModal: (intent) =>
    set({ loginModalOpen: true, authIntent: intent ?? null }),
  closeLoginModal: () => set({ loginModalOpen: false }),

  mobileNavOpen: false,
  setMobileNavOpen: (open) => set({ mobileNavOpen: open }),

  sidebarCollapsed: false,
  toggleSidebarCollapsed: () => {
    const next = !get().sidebarCollapsed;
    set({ sidebarCollapsed: next });
    persistSidebarCollapsed(next);
  },
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
}));
