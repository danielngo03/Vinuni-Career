export default function Loading() {
  return (
    <div className="grid min-h-[70vh] place-items-center bg-background">
      <div className="text-center">
        <div className="mx-auto size-9 animate-spin rounded-full border-2 border-blue-100 border-t-primary" />
        <p className="mt-4 text-sm font-medium text-muted">Loading workspace...</p>
      </div>
    </div>
  );
}
