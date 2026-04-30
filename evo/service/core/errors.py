from __future__ import annotations


class StateError(Exception):
    def __init__(  # noqa: B042
        self, code: str, message: str, details: dict | None = None, *, kind: str | None = None
    ) -> None:
        super().__init__(f'[{code}] {message}')
        self.code = code
        self.message = message
        self.details = dict(details or {})
        self.kind = kind

    def to_payload(self) -> dict:
        return {'code': self.code, 'message': self.message, 'details': dict(self.details)}
