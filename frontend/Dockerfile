# Phase 5 §5: the real `web` Compose service -- a real multi-stage
# production build (never `next dev` in a container). Pinned to a
# specific Node LTS patch release, not a floating "node:24" tag.
FROM node:24.14.0-bookworm-slim@sha256:d8e448a56fc63242f70026718378bd4b00f8c82e78d20eefb199224a4d8e33d8 AS base

# Phase 5 §7: a real trivy image scan found several real, already-
# patched Debian security updates not yet baked into this base image
# (libgnutls30 CVE-2026-33845 CRITICAL, perl-base CVE-2026-13221
# CRITICAL, among others), plus a real CRITICAL CVE-2026-59873 in
# `tar` bundled inside npm's own vendored dependencies (confirmed
# directly: `/usr/local/lib/node_modules/npm/node_modules/tar`, never
# invoked at this image's own runtime -- only `next start` runs --
# but still present in the image filesystem npm itself ships).
# `npm@latest` (12.2.1) requires node >=24.15.0/26 -- one patch above
# this image's own pinned 24.14.0 (confirmed directly, a real
# EBADENGINE failure) -- pinned to 11.21.1 instead, which supports
# node >=22.9.0 and bundles a real patched `tar@^7.5.22`. See
# docs/phase-5/evidence/trivy-*.log for the real before/after scan.
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/* \
    && npm install -g npm@11.21.1

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
