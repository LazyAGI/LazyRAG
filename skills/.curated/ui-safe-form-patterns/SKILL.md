---
name: ui-safe-form-patterns
description: Implement or refactor UI forms with defense-in-depth validation, safe input handling, reliable submission behavior, and privacy-aware error handling. Use when building login, registration, profile, payment, admin, or file-upload forms.
---

# UI Safe Form Patterns

Use this skill to build forms that are both secure and dependable in real user conditions.

## When to use
- Creating new forms or refactoring existing form logic.
- Hardening forms that process credentials, PII, money, or privileged actions.
- Fixing flaky submission flows and duplicate-submit bugs.

## Reliability and safety baseline
- Validate on both client and server.
- Treat client validation as UX, not security control.
- Normalize input before validation when format ambiguity is common.
- Prevent duplicate submissions with in-flight state and idempotent APIs.
- Use clear loading, success, retry, and failure states.
- Never leak secrets or raw backend traces in UI errors.

## Implementation workflow
1. Define schema and constraints per field, including max lengths and allowed character sets.
2. Build controlled input handling with immediate low-cost validation and deferred heavy checks.
3. Sanitize or encode displayed user-provided content in previews and confirmation screens.
4. Add submit lock, timeout handling, and cancel or retry behavior where relevant.
5. Map backend errors into safe user-facing messages without exposing internals.
6. Add tests for invalid input, race conditions, and repeated clicks.

## Sensitive field rules
- Password fields: enforce minimum policy and avoid logging or analytics capture.
- Email and phone: normalize before validation to reduce false negatives.
- File uploads: enforce MIME and size checks client-side and server-side.
- Rich text inputs: sanitize on server and encode on render.
- Numeric money fields: use decimal-safe parsing and range checks.

## Suggested checks
```bash
rg -n "onSubmit|handleSubmit|Form|formik|react-hook-form|yup|zod" frontend/src
rg -n "localStorage|sessionStorage|console\.log\(|Sentry|analytics" frontend/src
rg -n "type=\"file\"|upload|multipart|FormData" frontend/src
```

## Test minimum
- Reject malformed input with stable messaging.
- Ignore rapid double click while request is in flight.
- Preserve user input when recoverable errors occur.
- Avoid stale success state after failed retries.
- Confirm no sensitive values appear in logs or telemetry payloads.
