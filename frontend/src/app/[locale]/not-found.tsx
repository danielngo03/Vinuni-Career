import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="grid min-h-screen place-items-center bg-slate-50 px-4">
      <div className="max-w-md text-center">
        <p className="font-mono text-sm font-semibold text-primary">404</p>
        <h1 className="mt-3 text-3xl font-semibold">Workspace not found</h1>
        <p className="mt-3 text-sm leading-6 text-muted">
          The page may have moved or your active identity does not have access.
        </p>
        <Button asChild className="mt-6">
          <Link href="/vi">Return home</Link>
        </Button>
      </div>
    </main>
  );
}
