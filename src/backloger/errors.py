"""Stable application errors shared by all adapters."""


class BacklogError(Exception):
    code = "invalid_data"
    exit_code = 1
    http_status = 422


class ConflictError(BacklogError):
    code = "conflict"
    exit_code = 3
    http_status = 409


class ReadOnlyError(BacklogError):
    code = "read_only"
    exit_code = 4
    http_status = 403


class NotFoundError(BacklogError):
    code = "not_found"
    http_status = 404
