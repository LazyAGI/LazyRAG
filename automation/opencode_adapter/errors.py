from __future__ import annotations

from typing import Any, Dict, Optional


OPENCODE_BINARY_MISSING = 'OPENCODE_BINARY_MISSING'
OPENCODE_AUTH_MISSING = 'OPENCODE_AUTH_MISSING'
GIT_REPO_INVALID = 'GIT_REPO_INVALID'
BASE_REF_INVALID = 'BASE_REF_INVALID'
TARGET_FILE_MISSING = 'TARGET_FILE_MISSING'
OPENCODE_EXEC_FAILED = 'OPENCODE_EXEC_FAILED'
SCOPE_VIOLATION = 'SCOPE_VIOLATION'
NO_CHANGE = 'NO_CHANGE'


class AdapterError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(code, message, details)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_payload(self) -> Dict[str, Any]:
        return {
            'code': self.code,
            'message': self.message,
            'details': self.details,
        }
