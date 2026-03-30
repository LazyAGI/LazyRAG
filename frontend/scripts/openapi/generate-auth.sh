#!/bin/bash

set -e

export PATH="/opt/homebrew/opt/openjdk@17/bin:$PATH"

node scripts/openapi/generate-api.mjs auth
node scripts/openapi/generate-api.mjs core
