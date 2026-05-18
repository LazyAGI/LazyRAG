#!/bin/sh
set -eu

# Optional readonly schema (schema B) validation.
# Enable by setting:
# - LAZYMIND_READONLY_VALIDATE=1
# - LAZYMIND_READONLY_TABLES="ragservice.documents,ragservice.jobs"
#
# The actual validation logic runs inside /core at startup.

exec /core

