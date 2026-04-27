from __future__ import annotations


PERMANENT_CODES = frozenset({
    'OPENCODE_BIN_MISSING',
    'OPENCODE_AUTH_MISSING',
    'REPO_NOT_FOUND',
    'CHAT_DIR_NOT_FOUND',
    'CODE_MAP_EMPTY',
    'REPORT_INVALID',
    'STATE_DRIFT',
    'SCHEMA_FOLLOW_FAILED',
})

APPLY_ERROR_CODES = (
    'OPENCODE_BIN_MISSING',
    'OPENCODE_AUTH_MISSING',
    'OPENCODE_RUN_FAILED',
    'OPENCODE_NO_CHANGES',
    'OPENCODE_TIMEOUT',
    'APPLY_PATH_OUT_OF_ALLOWLIST',
    'REPO_NOT_FOUND',
    'CHAT_DIR_NOT_FOUND',
    'CODE_MAP_EMPTY',
    'REPORT_INVALID',
    'STATE_DRIFT',
    'GIT_DIFF_FAILED',
    'MAX_ROUNDS_EXCEEDED',
    'SCHEMA_FOLLOW_FAILED',
)


def classify(code: str) -> str:
    return 'permanent' if code in PERMANENT_CODES else 'transient'


class ApplyError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None,
                 *, kind: str | None = None) -> None:
        super().__init__(f'[{code}] {message}')
        self.code = code
        self.message = message
        self.details = dict(details or {})
        self.kind = kind or classify(code)

    def to_payload(self) -> dict:
        return {'code': self.code, 'kind': self.kind, 'message': self.message,
                'details': dict(self.details)}
