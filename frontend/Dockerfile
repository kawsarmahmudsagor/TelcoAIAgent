FROM node:20-alpine AS deps
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM node:20-alpine AS builder
WORKDIR /app
RUN corepack enable
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Baked into next.config.ts's /backend rewrite at build time (and read again at runtime by the
# landing page's server-side fetch, so compose also sets it as an environment variable).
ARG FASTAPI_INTERNAL_URL
ENV FASTAPI_INTERNAL_URL=${FASTAPI_INTERNAL_URL}
# Lint is skipped here: prettier fails on CRLF checkouts and pre-existing formatting
# drift, which shouldn't block producing an image. Run `pnpm lint` separately.
RUN pnpm exec next build --no-lint

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
