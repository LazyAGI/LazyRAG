# Build stage (optional: run pnpm build before docker build, or use multi-stage)
FROM nginx:alpine

# Copy built SPA from dist/ (run: pnpm build before docker build)
COPY dist/ /usr/share/nginx/html/
COPY default.conf /etc/nginx/conf.d/default.conf

# Legacy static app is in legacy/; use Dockerfile.legacy to serve that instead.
