import createMiddleware from "next-intl/middleware";
import { routing } from "./i18n/routing";

// Handles locale detection (Accept-Language) + explicit choice (URL prefix / NEXT_LOCALE cookie).
export default createMiddleware(routing);

export const config = {
  // Skip API routes, Next internals, and any path with a file extension (static assets).
  matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"],
};
