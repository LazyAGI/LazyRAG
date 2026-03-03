# Code Review Status

Status of the 64+ review suggestions. Algorithm submodule `algorithm/lazyllm` is reference-only and was not reviewed.

## Completed (first round + this round)

| # | Suggestion | Status |
|---|------------|--------|
| 1–5 | Unify reply/replyJSON; remove duplicate routes; doc/db use common.ReplyJSON | Done |
| 7–8 | Frontend: getAdminNavHTML, bindLogout, escapeHtml, loading | Done |
| 10 | validGranteeType, validPermission in acl | Done |
| 11–13 | Can() only GetKB for KB; remove _ = row; CallbackTask/TaskCallback comments | Done |
| 16 | chat ppl: asyncio.to_thread | Done |
| 21 | handleAPI perms: comment for extract_api_permissions | Done |
| 23 | Unify 403 body: common.ForbiddenBody, ProxyWithACL uses it | Done |
| 31 | /health: remove redundant Method check | Done |
| 32 | EnsureKB: drop redundant variable | Done |
| 33 | SetKBVisibility: single transaction for both tables | Done |
| 34 | AllKBIDs: single slice + map dedup | Done |
| 35 | algorithm/common/db: narrow exception types | Done |
| 37 | chat prompt: LAZYRAG_CHAT_PROMPT env, default English prompt | Done |
| 38–40 | chat import time; History EN; auth expires_in from jwt_ttl_seconds | Done |
| 43–44 | Frontend loading, XSS escapeHtml | Done |
| 48 | docker-compose healthcheck (auth-service, core); Kong depends_on healthy | Done |
| 50 | api/backend/core/openapi.yml: minimal placeholder | Done |
| 57 | Kong rbac-auth: timeout_ms configurable in schema | Done |

## Completed this round only

- **common**: `ForbiddenBody` constant; ProxyWithACL uses it (unified 403 format).
- **main**: handleAPI comment (perms for extract script); /health no redundant Method check.
- **acl/store**: EnsureKB simplify; SetKBVisibility in one transaction (gorm); AllKBIDs reuse slice + map.
- **algorithm/chat**: Prompt from `LAZYRAG_CHAT_PROMPT`, default English prompt.
- **api/backend/core/openapi.yml**: Minimal OpenAPI 3.0 placeholder.
- **kong/plugins/rbac-auth**: `timeout_ms` in schema and handler.

## Not done (by design or out of scope)

| # | Suggestion | Reason |
|---|------------|--------|
| 6 | Centralise sys.path.insert in algorithm | Each entry (chat/parsing/processor) is a script; PYTHONPATH set in Docker. Left as-is. |
| 9 | auth-service SessionLocal via DI/middleware | Architectural; would require broader refactor. |
| 14 | api_list_permission_groups .all() | Checked; SQLAlchemy 2 usage is correct. |
| 15 | Split /api/chat vs /api/chat/stream handler | Single handler is intentional; is_stream can be used later if needed. |
| 17 | ListKB total calculation | Logic was already correct (total before slice). |
| 18 | extract_api_permissions exclude | Logic verified; exclude applies to subdir names when scanning parent. |
| 19–20 | Proxy flushInterval type; Kong path normalize | Current behaviour is correct; no change. |
| 22, 24–30 | PathVar, parsePositiveInt to common, toString, _env_int, schemas, api retry, saveAuthState, route table | Low impact or stub code; deferred. |
| 36 | parsing store_config from env | Would require more env vars and parsing; deferred. |
| 41 | _require_admin cache user | Performance only; deferred. |
| 42 | Frontend API non-JSON response handling | Edge case; current catch(() => ({})) is acceptable. |
| 45–47 | DB connection doc, env naming, docker OPENSEARCH default | Documentation/config policy; not code change. |
| 49 | Graceful shutdown (Go/Python) | Can be added later; not in initial scope. |
| 51–55 | Tests, Makefile glob, requirements lock, go.mod | Test and CI improvements; deferred. |
| 56 | JWT secret in prod | Deployment/docs; not code. |
| 58–60 | Proxy body size limit; ListKB N+1; ACLsForUser cache | Performance; deferred. |
| 61–64 | Comments/errors i18n; structured logging; versioning | Consistency/docs; deferred. |

## Summary

- **Done**: All high-impact and most medium-impact items (unified responses, ACL/store cleanups, healthcheck, prompt from env, openapi placeholder, Kong timeout).
- **Left as “not done”**: Either already correct, architectural, performance, or documentation/CI follow-ups.
