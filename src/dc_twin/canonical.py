"""Strict JSON decoding and deterministic SHA-256 helpers."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from dc_twin.errors import ContractError, InvalidParameter


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(
                "contract.duplicate_key",
                f"Duplicate JSON key: {key}",
                invalid_params=(InvalidParameter(name=key, reason="duplicate key"),),
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ContractError(
        "contract.non_finite_number",
        f"Non-finite JSON number is not supported: {value}",
    )


def loads_strict(payload: str, *, max_bytes: int = 1_048_576) -> Any:
    """Decode JSON while rejecting duplicate keys, NaN, and oversized requests."""

    if len(payload.encode("utf-8")) > max_bytes:
        raise ContractError("contract.payload_too_large", "JSON payload exceeds 1 MiB.")
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except ContractError:
        raise
    except json.JSONDecodeError as exc:
        raise ContractError("contract.invalid_json", f"Invalid JSON: {exc.msg}") from exc
    except UnicodeDecodeError as exc:
        raise ContractError("contract.invalid_json", f"Invalid JSON: {exc.reason}") from exc
    assert_finite(value)
    return value


def load_path_strict(path: Path, *, max_bytes: int = 1_048_576) -> Any:
    """Read a bounded UTF-8 JSON file without following any embedded references."""

    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ContractError("contract.file_unreadable", f"Cannot read {path.name}: {exc}") from exc
    if size > max_bytes:
        raise ContractError("contract.payload_too_large", f"{path.name} exceeds 1 MiB.")
    try:
        return loads_strict(path.read_text(encoding="utf-8"), max_bytes=max_bytes)
    except UnicodeDecodeError as exc:
        raise ContractError("contract.invalid_encoding", f"{path.name} must be UTF-8.") from exc


def assert_finite(value: Any, *, path: str = "$") -> None:
    """Reject non-finite values recursively, including values built in memory."""

    if isinstance(value, float) and not math.isfinite(value):
        raise ContractError(
            "contract.non_finite_number",
            f"Non-finite number at {path}.",
            invalid_params=(InvalidParameter(name=path, reason="must be finite"),),
        )
    if isinstance(value, Mapping):
        for key, child in value.items():
            assert_finite(child, path=f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            assert_finite(child, path=f"{path}[{index}]")


def canonical_dumps(value: Any) -> str:
    """Return the canonical representation used by this model version."""

    assert_finite(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def sha256_json(value: Any) -> str:
    """Hash canonical UTF-8 JSON."""

    return hashlib.sha256(canonical_dumps(value).encode("utf-8")).hexdigest()
