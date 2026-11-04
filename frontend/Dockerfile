# Phase 5 §5: the real `web` Compose service -- a real multi-stage
# production build (never `next dev` in a container). Pinned to a
# specific Node LTS patch release, not a floating "node:24" tag.
FROM node:24.14.0-bookworm-slim@sha256:d8e448a56fc63242f70026718378bd4b00f8c82e78d20eefb199224a4d8e33d8 AS base

FROM base AS deps
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM base AS build
WORKDIR /app
RUN corepack enable
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN pnpm build

FROM base
WORKDIR /app
# A real, non-root user -- never run the real web process as root. The
# node:*-bookworm-slim base already ships a real "node" user at uid/gid
# 1000 (confirmed directly); reusing it rather than colliding with it by
# creating a second uid/gid 1000 identity.
COPY --from=build --chown=node:node /app/.next ./.next
COPY --from=build --chown=node:node /app/public ./public
COPY --from=build --chown=node:node /app/package.json ./package.json
COPY --from=build --chown=node:node /app/next.config.ts ./next.config.ts
COPY --from=deps --chown=node:node /app/node_modules ./node_modules
ENV NODE_ENV=production PORT=3000
USER node
EXPOSE 3000
CMD ["node_modules/.bin/next", "start", "--port", "3000"]
