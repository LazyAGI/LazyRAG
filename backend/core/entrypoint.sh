#!/bin/sh
set -eu

# Optional readonly schema (schema B) validation.
# Enable by setting:
# - LAZYRAG_READONLY_VALIDATE=1
# - LAZYRAG_READONLY_TABLES="ragservice.documents,ragservice.jobs"
#
# The actual validation logic runs inside /core at startup.

exec /core

