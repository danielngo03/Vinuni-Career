"use client";

import { useEffect, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "@/lib/api";
import { ToastProvider } from "@/components/ui";
import { useAuthStore } from "@/stores/auth-store";

/**
 * Restores the session once on app load (silent refresh + /auth/me). Renders
 * nothing; guards/components read status from the auth store.
 */
function SessionInit() {
  const hydrate = useAuthStore((s) => s.hydrate);
  useEffect(() => {
    void hydrate();
  }, [hydrate]);
  return null;
}

/** App-wide client providers: TanStack Query + Toast host. */
export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            refetchOnWindowFocus: false,
            retry: (failureCount, error) => {
              // Don't retry auth/permission/not-found — surface the right state.
              if (
                error instanceof ApiError &&
                (error.isAuthError ||
                  error.isPermissionError ||
                  error.isNotFound)
              ) {
                return false;
              }
              return failureCount < 2;
            },
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <SessionInit />
        {children}
      </ToastProvider>
    </QueryClientProvider>
  );
}
