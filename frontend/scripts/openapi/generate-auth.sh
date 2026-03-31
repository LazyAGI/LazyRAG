#!/bin/bash

set -e

if ! command -v java >/dev/null 2>&1; then
  echo 'Error: java not found. Install JDK 17+ and ensure it is on PATH (e.g. JAVA_HOME/bin).' >&2
  exit 1
fi

node scripts/openapi/generate-api.mjs auth
node scripts/openapi/generate-api.mjs core
