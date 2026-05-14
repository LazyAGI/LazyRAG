# Kong with custom rbac-auth plugin (needs lua-resty-http for auth-service calls)
ARG DOCKER_MIRROR=docker.m.daocloud.io/library/
FROM ${DOCKER_MIRROR}kong:3.6

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates \
    && luarocks install https://luarocks.org/manifests/pintsized/lua-resty-http-0.17.1-0.src.rock \
    && apt-get purge -y git \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*
USER kong

COPY plugins/rbac-auth /usr/local/share/lua/5.1/kong/plugins/rbac-auth
ENV KONG_PLUGINS=bundled,rbac-auth
