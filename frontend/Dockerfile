FROM node:22-alpine AS builder
WORKDIR /app

RUN corepack enable && corepack prepare pnpm@9.15.9 --activate

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

FROM nginx:alpine
WORKDIR /usr/share/nginx/html

COPY --from=builder /app/dist/ /usr/share/nginx/html/
COPY default.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 80
