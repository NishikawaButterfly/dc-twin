"""Dependency-light command line interface for validation, simulation, and replay."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from dc_twin.canonical import load_path_strict
from dc_twin.engine import simulate, verify_replay
from dc_twin.errors import ContractError, DCTwinError, InvariantError, TopologyError
from dc_twin.validation import parse_scenario, parse_snapshot

_MAX_PORT = 65535


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dc-twin",
        description="Deterministic capacity simulation using synthetic data.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    validate_design = subcommands.add_parser("validate-design", help="Validate a v1 design.")
    validate_design.add_argument("design", type=Path)

    validate_scenario = subcommands.add_parser("validate-scenario", help="Validate a v1 scenario.")
    validate_scenario.add_argument("design", type=Path)
    validate_scenario.add_argument("scenario", type=Path)

    run = subcommands.add_parser("run", help="Run a design and scenario.")
    run.add_argument("design", type=Path)
    run.add_argument("scenario", type=Path)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--force", action="store_true")

    replay = subcommands.add_parser("replay", help="Verify a result computation hash.")
    replay.add_argument("design", type=Path)
    replay.add_argument("scenario", type=Path)
    replay.add_argument("expected_result", type=Path)

    compare = subcommands.add_parser("compare", help="Compare deterministic result metrics.")
    compare.add_argument("left", type=Path)
    compare.add_argument("right", type=Path)

    serve = subcommands.add_parser("serve", help="Serve the local read-only API and web UI.")
    serve.add_argument("--host", default=os.getenv("DC_TWIN_HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.getenv("DC_TWIN_PORT", "8000")))
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        return _dispatch(arguments)
    except DCTwinError as exc:
        return _emit_error(exc)
    except OSError as exc:
        return _emit_error(ContractError("io.operation_failed", str(exc)), exit_code=4)


def _dispatch(arguments: argparse.Namespace) -> int:
    if arguments.command == "validate-design":
        snapshot = parse_snapshot(load_path_strict(arguments.design))
        return _emit(
            {"valid": True, "snapshot_id": snapshot.snapshot_id, "hash": snapshot.source_hash}
        )
    if arguments.command == "validate-scenario":
        snapshot = parse_snapshot(load_path_strict(arguments.design))
        scenario = parse_scenario(load_path_strict(arguments.scenario), snapshot)
        return _emit(
            {"valid": True, "scenario_id": scenario.scenario_id, "hash": scenario.source_hash}
        )
    if arguments.command == "run":
        snapshot = parse_snapshot(load_path_strict(arguments.design))
        scenario = parse_scenario(load_path_strict(arguments.scenario), snapshot)
        result = simulate(snapshot, scenario)
        _atomic_write_json(arguments.output, result, force=arguments.force)
        return _emit(
            {
                "run_id": result["run_id"],
                "computation_hash": result["computation_hash"],
                "output": str(arguments.output.resolve()),
            }
        )
    if arguments.command == "replay":
        snapshot = parse_snapshot(load_path_strict(arguments.design))
        scenario = parse_scenario(load_path_strict(arguments.scenario), snapshot)
        expected = load_path_strict(arguments.expected_result, max_bytes=20_000_000)
        if not isinstance(expected, dict) or not isinstance(expected.get("computation_hash"), str):
            raise ContractError(
                "result.missing_computation_hash",
                "Expected result does not contain a computation_hash string.",
            )
        verification = verify_replay(snapshot, scenario, expected["computation_hash"])
        _emit(verification)
        return 0 if verification["matches"] else 5
    if arguments.command == "compare":
        left = _result(load_path_strict(arguments.left, max_bytes=20_000_000), "left")
        right = _result(load_path_strict(arguments.right, max_bytes=20_000_000), "right")
        return _emit(_compare(left, right))
    if arguments.command == "serve":
        return _serve(arguments)
    raise InvariantError("cli.unknown_command", "Command dispatch failed.")


def _serve(arguments: argparse.Namespace) -> int:
    if arguments.host not in {"127.0.0.1", "localhost", "::1"}:
        raise ContractError(
            "server.non_loopback_host",
            "The CLI binds to loopback only; use a hardened reverse proxy for deployment.",
        )
    if not 1 <= arguments.port <= _MAX_PORT:
        raise ContractError("server.invalid_port", "Port must be from 1 through 65535.")
    # Imported lazily so every non-serve command keeps its fast start without the ASGI stack.
    import uvicorn  # noqa: PLC0415

    uvicorn.run(
        "dc_twin.api:app",
        host=arguments.host,
        port=arguments.port,
        log_level=os.getenv("DC_TWIN_LOG_LEVEL", "INFO").lower(),
        server_header=False,
    )
    return 0


def _result(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("metrics"), dict):
        raise ContractError("result.invalid", f"The {label} result has no metrics object.")
    return dict(value)


def _compare(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    metric_keys = sorted(set(left["metrics"]) | set(right["metrics"]))
    return {
        "left_run_id": left.get("run_id"),
        "right_run_id": right.get("run_id"),
        "same_computation": left.get("computation_hash") == right.get("computation_hash"),
        "metric_differences": {
            key: {"left": left["metrics"].get(key), "right": right["metrics"].get(key)}
            for key in metric_keys
            if left["metrics"].get(key) != right["metrics"].get(key)
        },
    }


def _atomic_write_json(path: Path, value: Any, *, force: bool) -> None:
    target = path.resolve()
    if target.exists() and not force:
        raise ContractError(
            "output.exists", f"Refusing to overwrite {target}; pass --force explicitly."
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            json.dump(
                value, temporary, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True
            )
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        Path(temporary_name).replace(target)
    except Exception:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
        raise


def _emit(value: Any) -> int:
    sys.stdout.write(json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True) + "\n")
    return 0


def _emit_error(error: DCTwinError, *, exit_code: int | None = None) -> int:
    body: dict[str, Any] = {"error_code": error.code, "detail": error.message}
    if error.invalid_params:
        body["invalid_params"] = [
            {"name": parameter.name, "reason": parameter.reason}
            for parameter in error.invalid_params
        ]
    sys.stderr.write(json.dumps(body, ensure_ascii=False, allow_nan=False, sort_keys=True) + "\n")
    if exit_code is not None:
        return exit_code
    if isinstance(error, InvariantError):
        return 3
    if isinstance(error, (ContractError, TopologyError)):
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
