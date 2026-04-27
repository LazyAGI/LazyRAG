#!/bin/sh
set -e

OC_DATA_DIR="${OPENCODE_DATA_DIR:-/var/lib/lazyrag/evo/opencode}"
mkdir -p "$OC_DATA_DIR"
chmod 700 "$OC_DATA_DIR"

LINK_TARGET="${HOME:-/root}/.local/share/opencode"
mkdir -p "$(dirname "$LINK_TARGET")"
if [ ! -L "$LINK_TARGET" ] && [ ! -e "$LINK_TARGET" ]; then
  ln -s "$OC_DATA_DIR" "$LINK_TARGET"
elif [ -L "$LINK_TARGET" ] && [ "$(readlink "$LINK_TARGET")" != "$OC_DATA_DIR" ]; then
  rm -f "$LINK_TARGET"
  ln -s "$OC_DATA_DIR" "$LINK_TARGET"
fi

if [ ! -f "$OC_DATA_DIR/auth.json" ]; then
  if [ -n "$EVO_OPENCODE_AUTH_JSON" ]; then
    printf '%s' "$EVO_OPENCODE_AUTH_JSON" > "$OC_DATA_DIR/auth.json"
  elif [ -n "$EVO_OPENCODE_ANTHROPIC_KEY" ]; then
    printf '{"anthropic":{"type":"api","key":"%s"}}' \
      "$EVO_OPENCODE_ANTHROPIC_KEY" > "$OC_DATA_DIR/auth.json"
  fi
fi

if [ "${EVO_BOOTSTRAP_PIP_INSTALL:-0}" = "1" ] && [ -f /app/evo/requirements.txt ]; then
  pip install -r /app/evo/requirements.txt
fi

exec uvicorn evo.service.api:get_app --factory --host 0.0.0.0 --port 8047
