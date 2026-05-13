---
name: ui-secure-review
description: Review frontend and UI changes for concrete security risks such as XSS, unsafe URL handling, token leakage, missing origin checks, and client-side authorization gaps. Use when users ask for a UI code review focused on safety and reliability.
---

# UI Secure Review

Use this skill when the user asks for a frontend review with a security-first lens.

## When to use
- Reviewing PRs that touch UI rendering, routing, auth, storage, or API calls.
- Auditing React, Vue, or plain JavaScript UI code for exploitable patterns.
- Hardening existing UI code before release.

## When not to use
- Pure visual polish work with no logic or data handling changes.
- Backend-only or infra-only changes.

## Review workflow
1. Map changed files and rank risk by feature type.
2. Run quick pattern scans for dangerous APIs and sinks.
3. Read high-risk files in detail and trace data from input to render.
4. Confirm exploitability, impact, and realistic attack path.
5. Report findings ordered by severity with exact file and line references.
6. Suggest minimum safe fix and regression tests for each finding.

## High-risk patterns to check
- HTML injection: `dangerouslySetInnerHTML`, `v-html`, `innerHTML`, `outerHTML`.
- Script execution: `eval`, `new Function`, string-based timers.
- URL and navigation sinks: dynamic `href`, `window.open`, router redirects from untrusted params.
- Tabnabbing risk: external links with `target="_blank"` missing `rel="noopener noreferrer"`.
- Token exposure: auth tokens in query params, logs, localStorage, or error traces.
- Cross-origin trust: `postMessage` without strict `origin` and `source` checks.
- Client-only authorization assumptions that can be bypassed in browser devtools.
- Sensitive data persistence in cache, URL, or browser storage.

## Quick scan commands
Use these patterns as a first pass, then manually verify context.

```bash
rg -n "dangerouslySetInnerHTML|v-html|innerHTML|outerHTML|eval\(|new Function\(" frontend/src
rg -n "window\.open|postMessage|target=\"_blank\"|localStorage|sessionStorage" frontend/src
rg -n "token|authorization|auth|redirect|location\.href|router\.push" frontend/src
```

## Fix guidance
- Prefer safe templating and escaped rendering over raw HTML insertion.
- Validate and normalize all dynamic URLs before navigation.
- Keep tokens in secure httpOnly cookies when architecture allows.
- Add strict allowlists for cross-origin messaging and navigation targets.
- Enforce authorization on the server even if UI hides actions.

## Output contract
- Findings first, ordered by severity.
- Include file path, line, risk, exploit scenario, and concrete fix.
- Explicitly say "No high-confidence findings" if nothing actionable is found.
- Mention residual test gaps or assumptions.
