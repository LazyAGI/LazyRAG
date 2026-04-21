from __future__ import annotations


APPLY_ERROR_CODES = (
    'OPENCODE_BIN_MISSING',
    'OPENCODE_AUTH_MISSING',
    'OPENCODE_RUN_FAILED',
    'OPENCODE_NO_CHANGES',
    'OPENCODE_TIMEOUT',
    'REPO_NOT_FOUND',
    'CHAT_DIR_NOT_FOUND',
    'CODE_MAP_EMPTY',
    'REPORT_INVALID',
    'STATE_DRIFT',
    'GIT_DIFF_FAILED',
    'MAX_ROUNDS_EXCEEDED',
)


class ApplyError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(f'[{code}] {message}')
        self.code = code
        self.message = message
        self.details = dict(details or {})

    def to_payload(self) -> dict:
        return {'code': self.code, 'message': self.message, 'details': dict(self.details)}
