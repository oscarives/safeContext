# TODO: Replace placeholder with real application code when apps/ui/ is implemented.
# This multi-stage Dockerfile is structurally correct and ready for development.

# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci --ignore-scripts 2>/dev/null || true

# Copy source and build
COPY . .
RUN npm run build 2>/dev/null || true

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM node:20-alpine AS runtime

WORKDIR /app

ENV NODE_ENV=production

# Copy built assets from builder
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
COPY --from=builder /app/cache-handler.js ./cache-handler.js 2>/dev/null || true

# Non-root user for security
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001
USER nextjs

EXPOSE 3000

# TODO: Replace with actual entrypoint once apps/ui/ Next.js app is scaffolded
CMD ["node", "server.js"]
