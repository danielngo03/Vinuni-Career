# VinUni Career Platform — frontend (Next.js 15 standalone) image for Cloud Run.
#
# NEXT_PUBLIC_* values are baked in AT BUILD TIME (Next.js inlines them), so the
# backend URL must be passed as build args, not runtime env:
#
#   docker build \
#     --build-arg NEXT_PUBLIC_APP_URL=https://career.example.com \
#     --build-arg NEXT_PUBLIC_API_URL=https://<backend-cloud-run-url> \
#     -t vinuni-career-web .
#
# NEXT_PUBLIC_API_BASE_URL stays `/api/v1` (relative): the browser talks to the
# frontend origin and the Next.js rewrite proxies to NEXT_PUBLIC_API_URL, which
# keeps the httpOnly refresh cookie same-origin (see next.config.ts).

FROM node:22-alpine AS deps

RUN npm install -g pnpm@11

WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile


FROM node:22-alpine AS build

RUN npm install -g pnpm@11

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG NEXT_PUBLIC_APP_URL=http://localhost:3000
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_API_BASE_URL=/api/v1
ARG NEXT_PUBLIC_DEFAULT_LOCALE=vi
ARG NEXT_PUBLIC_SUPPORTED_LOCALES=vi,en

ENV NEXT_PUBLIC_APP_URL=$NEXT_PUBLIC_APP_URL \
    NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_PUBLIC_DEFAULT_LOCALE=$NEXT_PUBLIC_DEFAULT_LOCALE \
    NEXT_PUBLIC_SUPPORTED_LOCALES=$NEXT_PUBLIC_SUPPORTED_LOCALES \
    NEXT_TELEMETRY_DISABLED=1

RUN pnpm build


FROM node:22-alpine

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0

COPY --from=build /app/public ./public
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static

USER node
EXPOSE 8080

# Next standalone server honors $PORT (Cloud Run injects it).
CMD ["node", "server.js"]
