---
name: ui-resilient-accessibility
description: Build and review UI components for robust accessibility and runtime resilience, including semantic structure, keyboard support, loading and error states, retry flows, and predictable async behavior.
---

# UI Resilient Accessibility

Use this skill when a UI must remain usable, accessible, and stable under imperfect conditions.

## When to use
- Shipping new pages, complex components, or interactive widgets.
- Fixing regressions caused by async loading, race conditions, or keyboard traps.
- Preparing admin or customer-facing UI for production readiness.

## Core principles
- Semantics first: prefer native HTML elements before custom role emulation.
- Keyboard complete: every actionable element must be operable without a mouse.
- State explicitness: always define `loading`, `empty`, `success`, and `error` states.
- Async predictability: handle cancellation, stale responses, and rapid re-requests.
- Failure recovery: give users clear next steps and safe retry behavior.

## Delivery workflow
1. Define state model for each async view before coding UI details.
2. Implement semantic markup and accessible names for controls and regions.
3. Add focus management for dialogs, drawers, and route transitions.
4. Guard against out-of-order responses and set-state-after-unmount issues.
5. Provide clear empty and error messages with retry paths.
6. Validate with keyboard-only walkthrough and screen-reader-friendly labels.

## Reliability checks
- Disable unsafe repeat actions while requests are pending.
- Ensure retries do not duplicate side effects for non-idempotent operations.
- Render skeleton or loading indicators that do not shift layout excessively.
- Preserve critical user context after transient failures.
- Fail closed for privileged actions when permission data is uncertain.

## Accessibility checks
- One clear page heading hierarchy.
- Inputs have associated labels and error text linked via `aria-describedby`.
- Modals trap focus and restore focus on close.
- Contrast and focus indicators are visible.
- Announce async status changes where needed (`aria-live`).

## Suggested checks
```bash
rg -n "aria-|role=|tabIndex|onKeyDown|onKeyUp|onClick" frontend/src
rg -n "loading|isLoading|error|retry|empty|skeleton" frontend/src
rg -n "useEffect|AbortController|cleanup|unmount|stale" frontend/src
```
