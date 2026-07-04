export function sectionsToText(data: { sections?: unknown[] } | null | undefined): string {
  if (!data?.sections?.length) return "";
  return data.sections
    .map((s) => {
      const sec = s as Record<string, unknown>;
      const title = String(sec.title ?? "");
      const content = sec.content as { items?: unknown[] } | undefined;
      const items = Array.isArray(content?.items) ? content.items : [];
      const lines = items.map((it) =>
        String((it as Record<string, unknown>).text ?? it ?? "")
      );
      return [title, ...lines].filter(Boolean).join("\n");
    })
    .join("\n\n");
}
