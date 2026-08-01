"""Stable domain errors used by the CLI and RFC 9457 API responses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class InvalidParameter:
    """A machine-readable invalid-input location."""

    name: str
    reason: str


class DCTwinError(Exception):
    """Base error with a stable public code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 422,
        invalid_params: tuple[InvalidParameter, ...] = (),
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.invalid_params = invalid_params
        self.details = details or {}


class ContractError(DCTwinError):
    """Input does not conform to a supported contract."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        invalid_params: tuple[InvalidParameter, ...] = (),
    ) -> None:
        super().__init__(code, message, invalid_params=invalid_params)


class TopologyError(DCTwinError):
    """A syntactically valid topology cannot be simulated safely."""


class InvariantError(DCTwinError):
    """The engine detected an impossible internal state."""


class ResourceLimitError(DCTwinError):
    """A documented synchronous processing limit was exceeded."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, status_code=413)
