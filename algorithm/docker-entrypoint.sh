#!/bin/sh
# Entrypoint: apply image-baked defaults for env vars that are unset or empty.
# Runtime-provided values (from docker-compose environment, docker run -e,
# k8s env, etc.) always take precedence and will NOT be overridden.
set -e

# Required by runtime_models.inner.yaml (llm role -> minimax).
# Internal deployment key; safe to bake into image per project policy.
: "${LAZYLLM_MINIMAX_API_KEY:=sk-maas-GDZmEQsilc4uGXXTaWnIHmET9V0eenZ8F6eWk3LaPzE}"
export LAZYLLM_MINIMAX_API_KEY

exec "$@"
