/**
 * Auth route group layout — no header, no footer.
 * Auth pages (login, register, verify-email, etc.) render in a centered full-screen
 * layout with no PublicShell navigation. The AuthShell card is self-contained.
 */
export default function AuthGroupLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[var(--bg-surface)] antialiased">
      {children}
    </div>
  );
}
