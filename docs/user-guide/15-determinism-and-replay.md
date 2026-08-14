# 15. Result hashes, determinism and replay

Determinism is what makes a dc-twin result quotable. It converts "believe my
table" into "run it yourself and compare sixty-four hex characters". This
chapter shows exactly what the guarantee covers and, more importantly, what it
does not.

## The three hashes

Every result carries three:

| Field | Covers |
|---|---|
| `snapshot_hash` | SHA-256 of the canonical snapshot JSON |
| `scenario_hash` | SHA-256 of the canonical scenario JSON |
| `computation_hash` | SHA-256 of the deterministic semantic result, excluding `run_id` and the hash field itself |

Canonical JSON means UTF-8, recursively sorted object keys, `,` and `:`
separators with no optional whitespace, preserved Unicode, and no non-finite
values. Two documents that differ only in key order or indentation hash
identically; two that differ in a single digit do not.

`run_id` is derived, not independent: `run-` plus the first 16 hex characters
of the computation hash. Two results with the same `run_id` are the same
computation.

You can get the input hashes without running anything:

```powershell
dc-twin validate-design guide-2n.snapshot.json
dc-twin validate-scenario guide-2n.snapshot.json feed-loss-2n.scenario.json
```

```json
{"hash": "c6c6f02446315f5a99e46df429d6a9575784f0bfb72a0878a862551a0f97b98b", "snapshot_id": "guide-2n", "valid": true}
{"hash": "032b0185ca17a4ea1641e625a1a47459d4006a6f1d6769fec5bb06f333290175", "scenario_id": "GUIDE-2N-FEED-LOSS", "valid": true}
```

## The guarantee

> Same canonical inputs, same engine version, same computation hash. Always.

Not "usually", not "on the same platform". The kernel sorts source identifiers
and adjacency lists before traversal specifically so the answer cannot depend
on dictionary order, filesystem order or database order. Energy accounting is
integer, so it cannot depend on floating-point behaviour.

Run the same inputs twice into different files:

```powershell
dc-twin run guide-2n.snapshot.json feed-loss-2n.scenario.json --output results/a.json
dc-twin run guide-2n.snapshot.json feed-loss-2n.scenario.json --output results/b.json
dc-twin compare results/a.json results/b.json
```

```json
{"left_run_id": "run-72e2cb542c7489b9", "right_run_id": "run-72e2cb542c7489b9", "same_computation": true, "metric_differences": {}}
```

## Verifying a replay

`replay` recomputes from the inputs and compares against a stored result's
hash:

```powershell
dc-twin replay guide-2n.snapshot.json feed-loss-2n.scenario.json results/a.json
```

```json
{"actual_computation_hash": "72e2cb542c7489b99f40fac14d0d43f777719798d084dcd3783cf2094f2b5bbb", "expected_computation_hash": "72e2cb542c7489b99f40fac14d0d43f777719798d084dcd3783cf2094f2b5bbb", "matches": true, "replay_run_id": "run-72e2cb542c7489b9"}
```

Exit code 0. A mismatch exits 5 and reports both hashes:

```json
{"actual_computation_hash": "3bb8a47aa442f0e04834cd32a59ce70d8a0c6f4e91584656a93d68794956f2b5", "expected_computation_hash": "72e2cb542c7489b99f40fac14d0d43f777719798d084dcd3783cf2094f2b5bbb", "matches": false, "replay_run_id": "run-3bb8a47aa442f0e0"}
```

A `matches: false` is never coerced to success. It is evidence of semantic
drift and should fail a release gate.

The API has the same operation at `POST /api/v1/runs/{run_id}/replay`, which
recomputes the bundled fixture behind a retained run without mutating the
original record.

The bundled fixtures verify identically across interfaces. Running
`REF-DC-2N-001` through the CLI and through the API both yield
`71c0ef262cfc15d0fd449b53adcbad62c8c51418ab33d211f64031e01c77b5a0`.

## Proving the hash moves

Two experiments, both on the chapter 3 redundant pair, both changing exactly
one integer.

### Experiment one: change the failure time by 1 ms

Move the utility failure from 60,000 ms to 60,001 ms.

```json
{"computation_hash": "3bb8a47aa442f0e04834cd32a59ce70d8a0c6f4e91584656a93d68794956f2b5", "run_id": "run-3bb8a47aa442f0e0"}
```

Base hash `72e2cb54…`, new hash `3bb8a47a…`. One millisecond, an entirely
different fingerprint. That is the collision resistance of SHA-256 doing its
job: there is no such thing as a "close" hash.

### Experiment two: change only the reporting resolution

Change `resolution_ms` from 1,000 to 2,000 and nothing else.

```json
{"computation_hash": "8080c8c42df260ffc375238d4aeadb349ef8c2fb494ac69604822c5c5bd73398", "run_id": "run-8080c8c42df260ff"}
```

Now compare:

```powershell
dc-twin compare results/2n-res1000.json results/2n-res2000.json
```

```json
{"left_run_id": "run-72e2cb542c7489b9", "metric_differences": {}, "right_run_id": "run-8080c8c42df260ff", "same_computation": false}
```

**Every metric is identical and the hash is different.** This is the single most
important thing to understand about the hash.

## What the hash covers, and what that means for you

The computation hash covers the whole semantic result: metrics, every timeline
segment, every transition, every alarm, every telemetry point and every
explanation. The timeline is part of the result, and resolution changes the
timeline, so resolution changes the hash.

Three consequences follow.

**A differing hash does not mean a differing answer.** Two runs can disagree on
the hash and agree on every metric, every alarm, and the physical story. The
resolution experiment above is exactly that case. Read `same_computation:
false` as "these are not the same computation", never as "these designs behave
differently".

**A matching hash is a very strong statement.** It means the entire semantic
result is identical, down to the last telemetry point. That is what makes it
useful as a regression gate.

**Cosmetic input changes move the hash.** Because the snapshot and scenario
hashes cover the documents as written, editing a `label`, adding an
`assumptions` line, correcting a typo in `provenance.method`, or renaming a
component all change the computation hash while changing nothing physical.
Chapter 2's kind-swap experiment is the clean demonstration: swapping
`transformer` for `switchgear` moved the computation hash while leaving every
metric, every flow, every alarm and every per-segment state hash untouched.

So the hash answers "is this the same run", not "is this the same conclusion".
Those are different questions and you need both.

## The per-segment state hash

Each timeline segment carries its own `state_hash`, a SHA-256 of the canonical
runtime state at `end_ms`: component statuses, connection positions, running
generators, demands, battery energies, and which alarms have latched.

These are more useful than the top-level hash for diagnosis, because they are
comparable *within* a run. A long run of identical state hashes is a stable
period; the segment where the hash changes is where something actually changed.
Transitions record the before and after state hash for exactly this reason.

Note what the state hash excludes: ratings, kinds, labels — anything that
cannot change during a run. This is why the kind-swap experiment produced an
identical sequence of state hashes across two different snapshots.

## What determinism does not give you

This is the part to hold on to.

**Determinism is not accuracy.** The engine will reproduce a wrong answer
exactly as reliably as a right one. If your UPS energy figure is off by 20%,
every run reproduces that error to the millisecond, forever, with a stable
hash and a passing replay.

**A matching hash validates nothing about equipment.** The web explorer says
this on the provenance panel and it is worth repeating: a matching hash
supports reproducibility; it does not validate real-world equipment or
operation. It proves the software computed the same thing twice. It says
nothing about whether the thing computed corresponds to a facility.

**Replay does not re-verify the inputs against reality.** It re-runs the same
JSON. If the JSON was wrong when you wrote it, replay confirms it is still
wrong in the same way.

Determinism buys you one thing, and it is worth having: it removes the tool
from the list of things that could explain a disagreement. If two engineers
get different answers from dc-twin, they have different inputs. That is a
genuinely valuable property and it is the only one on offer.

## Recording provenance with a result

When you quote a run, record all four identifiers. They fit on one line:

```text
engine 1.0.0
snapshot_hash    c6c6f02446315f5a99e46df429d6a9575784f0bfb72a0878a862551a0f97b98b
scenario_hash    da0c3b24bfd8e28a975b7150e925241952b7d4c15696a8e0f43add2c933aa2c3
computation_hash 5ae8c11939145806c5d794ebb6777c734e0d0448c9155305aef8b1a8d4700a39
```

With those, anyone holding the same two input files can reproduce your result
exactly, and anyone holding a *different* input file can prove it is different
without reading it.

---

Previous: [14. Stranded capacity](14-stranded-capacity.md) ·
Next: [16. Comparing two scenarios](16-comparing-scenarios.md)
