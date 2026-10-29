# SecBrain frontend image (Next.js standalone output)
FROM node:22-slim AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
# API base is resolved at runtime in the browser (see lib/api.ts). These are
# only used if you pin a fixed URL/port; leaving NEXT_PUBLIC_API_URL empty makes
# the browser derive the API from the host it's opened on.
ARG NEXT_PUBLIC_API_URL=
ARG NEXT_PUBLIC_API_PORT=8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_API_PORT=${NEXT_PUBLIC_API_PORT}
RUN npm run build

FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
RUN useradd -m -u 10002 nextuser
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
USER nextuser
EXPOSE 3000
CMD ["node", "server.js"]
