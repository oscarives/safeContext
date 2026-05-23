# ── Stage 1: dependencies ─────────────────────────────────────────────────────
FROM node:24.16.0-alpine AS deps

WORKDIR /app
COPY package.json package-lock.json ./
# npm install (not npm ci) to regenerate the lock file after Node 24 upgrade.
# The lock file will be updated on the first build; commit the result afterwards
# to restore strict reproducibility via npm ci.
RUN npm install --legacy-peer-deps

# ── Stage 2: builder ──────────────────────────────────────────────────────────
FROM node:24.16.0-alpine AS builder

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ── Stage 3: runtime ──────────────────────────────────────────────────────────
FROM node:24.16.0-alpine AS runtime

WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

# Copy built output
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
# public/ may be empty in minimal setup — copy only if it exists
COPY --from=builder /app/public ./public
COPY --from=builder /app/cache-handler.js ./cache-handler.js

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --start-period=45s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000/api/health || exit 1

CMD ["node", "server.js"]
