import type { Locale } from "./config";
import vi from "@/messages/vi.json";
import en from "@/messages/en.json";

const dictionaries = { vi, en } as const;

export function getDictionary(locale: Locale) {
  return dictionaries[locale];
}

export type Dictionary = ReturnType<typeof getDictionary>;
