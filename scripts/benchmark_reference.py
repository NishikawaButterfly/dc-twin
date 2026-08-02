"""Bounded, reproducible reference benchmark with environment disclosure."""

from __future__ import annotations

import json
import platform
import statistics
import sys
import time

from dc_twin.engine import simulate
from dc_twin.reference import ReferenceCatalog


def main() -> int:
    catalog = ReferenceCatalog.load()
    reference = catalog.scenarios["REF-DC-2N-001"]
    snapshot = catalog.snapshot_for(reference.scenario).snapshot
    durations_ms: list[float] = []
    hashes: set[str] = set()
    for _ in range(5):
        started = time.perf_counter_ns()
        result = simulate(snapshot, reference.scenario)
        durations_ms.append((time.perf_counter_ns() - started) / 1_000_000)
        hashes.add(str(result["computation_hash"]))
    if len(hashes) != 1:
        raise RuntimeError("Benchmark replays produced different computation hashes.")
    evidence = {
        "scenario_id": reference.scenario.scenario_id,
        "iterations": len(durations_ms),
        "median_duration_ms": round(statistics.median(durations_ms), 3),
        "minimum_duration_ms": round(min(durations_ms), 3),
        "maximum_duration_ms": round(max(durations_ms), 3),
        "computation_hash": hashes.pop(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "claim_scope": "Observed benchmark evidence only; not a production capacity guarantee.",
    }
    sys.stdout.write(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
