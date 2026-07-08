import { getRequestConfig } from "next-intl/server";
import { routing, type AppLocale } from "./routing";
import { loadMessages } from "@/messages/load";

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale: AppLocale = routing.locales.includes(requested as AppLocale)
    ? (requested as AppLocale)
    : routing.defaultLocale;

  return {
    locale,
    messages: await loadMessages(locale),
  };
});
