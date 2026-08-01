"""Environment-configured ASGI process entry point for the container image."""

from __future__ import annotations

import os

import uvicorn

from dc_twin.errors import ContractError

_MAX_PORT = 65535


def main() -> int:
    host = os.getenv("DC_TWIN_HOST", "127.0.0.1")
    # The wildcard address is deliberate: the hardened container publishes this port itself.
    if host not in {"127.0.0.1", "0.0.0.0", "::1", "::"}:  # noqa: S104
        raise ContractError(
            "server.invalid_host", "DC_TWIN_HOST must be an explicit local bind address."
        )
    try:
        port = int(os.getenv("DC_TWIN_PORT", "8000"))
    except ValueError as exc:
        raise ContractError("server.invalid_port", "DC_TWIN_PORT must be an integer.") from exc
    if not 1 <= port <= _MAX_PORT:
        raise ContractError("server.invalid_port", "DC_TWIN_PORT must be from 1 through 65535.")
    log_level = os.getenv("DC_TWIN_LOG_LEVEL", "INFO").lower()
    if log_level not in {"critical", "error", "warning", "info", "debug"}:
        raise ContractError("server.invalid_log_level", "DC_TWIN_LOG_LEVEL is not supported.")
    uvicorn.run(
        "dc_twin.api:app",
        host=host,
        port=port,
        log_level=log_level,
        server_header=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
