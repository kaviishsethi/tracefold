from __future__ import annotations


class ApiError(Exception):
    """An error that maps to the documented error envelope. Messages never carry private text."""

    def __init__(self, status: int, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable


def not_found() -> ApiError:
    return ApiError(404, "not_found", "Resource not found.")
