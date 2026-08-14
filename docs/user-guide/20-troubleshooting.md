# 20. Troubleshooting

Every message in this chapter was produced by running the command shown. The
engine fails closed: an invalid model is never coerced into a plausible-looking
simulation.

## How to read a failure

Errors are one line of JSON on stderr with a stable `error_code`, a
human-readable `detail`, and sometimes `invalid_params` pointing at the exact
JSON path:

```json
{"detail": "Invalid value at $.components[0]: unexpected fields: voltage_v", "error_code": "contract.invalid_field", "invalid_params": [{"name": "$.components[0]", "reason": "unexpected fields: voltage_v"}]}
```

Branch on `error_code`. The families are:

| Family | Meaning |
|---|---|
| `contract.*` | JSON shape, unit, version, identifier, or resource-limit rejection |
| `topology.*` | Unsupported or impossible graph structure |
| `scenario.*` | Invalid event target, state, reference, or timing |
| `engine.*` | Internal invariant failure — a bug; please report it |
| `output.*`, `io.*` | Filesystem problems |
| `server.*` | `serve` argument problems |
| `reference.*`, `run.*`, `replay.*` | API lookup and replay failures |

Exit codes are covered in chapter 10. Note that resource-limit rejections exit
`1` while contract and topology rejections exit `2`.

## Snapshot problems

### `topology.cycle_not_supported`

```json
{"detail": "Directed cycle detected at pdu-a; v1 supports DAG topologies only.", "error_code": "topology.cycle_not_supported"}
```

You have a loop. Usually this is a tie or ring bus modelled with edges in both
directions. Version 1 supports directed acyclic graphs only: choose one
direction for the tie and accept that flow the other way is not modelled, or
model the two operating configurations as two snapshots.

### `topology.load_not_terminal`

```json
{"detail": "Load it-load-1 must be a terminal node.", "error_code": "topology.load_not_terminal"}
```

Something is connected downstream of a load. If you were modelling a
sub-distribution board, make it a `pdu` and put the loads at the ends.

### `topology.broken_reference`

```json
{"detail": "Connection utility-a-to-switchgear-a references unknown source utility-z.", "error_code": "topology.broken_reference"}
```

A connection names a component that does not exist. Almost always a typo or a
component renamed without updating its edges.

### `topology.parallel_sources` (in the snapshot)

```text
ats-a has more than one initially closed input; v1 forbids paralleling.
```

An ATS or STS starts with two closed inputs. Exactly one input may be closed
initially. In the bundled fixtures the generator tie is `initial_closed: false`
for this reason.

### `contract.invalid_field` on `path`

```json
{"detail": "Invalid value at $.components[0].path: must be A, B, or shared", "error_code": "contract.invalid_field"}
```

Only `A`, `B` and `shared` are accepted. There is no third path. If you are
modelling three feeds, you cannot label them in a way the redundancy evidence
will understand — see chapter 5.

### `contract.invalid_field` with `unexpected fields`

```json
{"detail": "Invalid value at $.components[0]: unexpected fields: voltage_v", "error_code": "contract.invalid_field"}
```

The parser accepts no field it does not know, at any depth. There is nowhere to
record voltage, cable size, asset tags or manufacturer data.

The same check catches *missing* fields, and the required set depends on kind: a
`load` needs `demand_w`, `priority` and `service_order`; a `ups` needs
`usable_energy_mj` and `low_energy_threshold_pct`; a `generator` needs
`start_delay_ms`.

### `contract.invalid_field` on `data_classification`

```json
{"detail": "Invalid value at $.data_classification: public fixtures must be classified synthetic", "error_code": "contract.invalid_field"}
```

The value must be the string `synthetic`. This is a deliberate policy gate; see
[DATA_PROVENANCE.md](../DATA_PROVENANCE.md).

## Scenario problems

### `contract.invalid_field` on `snapshot_id`

```json
{"detail": "Invalid value at $.snapshot_id: does not match the supplied design snapshot", "error_code": "contract.invalid_field"}
```

The scenario names a different snapshot than the one on the command line. This
is the most common error when copying a scenario to a new topology — it is
always the first field to change.

### `scenario.invalid_target`

```json
{"detail": "Event event-002-gen requires a generator target.", "error_code": "scenario.invalid_target"}
```

A `generator_running` or `generator_start_failure` aimed at something that is
not a generator, or a `load_step` aimed at something that is not a load.

### `scenario.load_above_rating`

```json
{"detail": "Event event-002-step sets demand above it-load-1's rating.", "error_code": "scenario.load_above_rating"}
```

A `load_step` exceeds the load component's own `capacity_w`, which acts as its
maximum authorised demand. Raise the component's rating or lower the step.

### `scenario.contradictory_events`

```json
{"detail": "Multiple events target utility-a at 60000 ms.", "error_code": "scenario.contradictory_events"}
```

Two events on the same component at the same millisecond. One event per
component per timestamp. Transfers are exempt because they target connections.

### `scenario.generator_without_source_loss`

```json
{"detail": "Event event-001-generator-a-running has no preceding same-path utility failure in v1.", "error_code": "scenario.generator_without_source_loss"}
```

Version 1 models reactive starts only. Every generator outcome must follow a
`component_failure` on a **utility tagged with the same path** as the
generator. There is no way to model a pre-emptive start, a load-bank test or a
peak-shaving run.

### `scenario.generator_start_too_early`

```json
{"detail": "Event event-002-generator-a-running occurs after 10000 ms, below generator-a's 15000 ms start delay.", "error_code": "scenario.generator_start_too_early"}
```

Move the outcome to at least `start_delay_ms` after the qualifying utility
loss, or reduce the generator's declared delay.

### `contract.invalid_field` on `time_ms`

```json
{"detail": "Invalid value at $.events[0].time_ms: must be an integer from 0 through 600000", "error_code": "contract.invalid_field"}
```

An event falls outside the horizon. Either move the event or extend
`horizon_ms`.

## Resource-limit problems

### `contract.timeline_limit`

```json
{"detail": "Scenario would exceed 10000 timeline segments.", "error_code": "contract.timeline_limit"}
```

Exit code `1`. Your resolution is too fine for your horizon:

```text
segments ≈ ceil(horizon_ms / resolution_ms) + event_count + 2 × ups_count
```

Measured on a one-UPS, one-event topology: a 600,000 ms horizon accepts 61 ms
and rejects 60 ms; a seven-day horizon accepts 61,000 ms and rejects 60,000 ms.
Coarsen the resolution or shorten the horizon. Chapter 9 explains why coarsening
does not cost accuracy.

### `contract.telemetry_limit`

The parallel ceiling at 250,000 points, where points per segment are
`4 + ups_count + load_count + source_count`. A topology with many loads hits
this before the segment limit.

### `contract.component_limit`, `contract.connection_limit`, `contract.event_limit`

250 components, 500 connections, 1,000 external events.

## Run-time problems

### `topology.parallel_sources` after validation passed

This is the one that catches people, because it appears *only* at run time:

```powershell
dc-twin validate-scenario examples/synthetic/reference-2n.snapshot.json parallel.scenario.json
```

```json
{"hash": "784d78756746c14eeac272a19fff9b002cbe2d7fb92256d6fe6e8d65593c9dd2", "scenario_id": "GUIDE-PARALLEL", "valid": true}
```

```powershell
dc-twin run examples/synthetic/reference-2n.snapshot.json parallel.scenario.json --output results/parallel.json
```

```json
{"detail": "Runtime transfer would parallel inputs at ats-a: utility-a-to-ats-a, generator-a-to-ats-a.", "error_code": "topology.parallel_sources"}
```

A transfer closed a second input at an ATS or STS without opening the first.
Put the open and the close in the same `atomic_transfer` event — that is the
correct pattern and chapter 8 shows it.

The general lesson: **`validate-scenario` passing does not guarantee the run
will complete.** Structural validation cannot see state that only exists
mid-simulation.

### `output.exists`

```json
{"detail": "Refusing to overwrite C:\\...\\results\\composite.json; pass --force explicitly.", "error_code": "output.exists"}
```

Deliberate. Pass `--force` when you mean to replace a result.

### `contract.file_unreadable`

```json
{"detail": "Cannot read does-not-exist.json: [WinError 2] The system cannot find the file specified: 'bad\\\\does-not-exist.json'", "error_code": "contract.file_unreadable"}
```

Check the path. Note that dc-twin resolves paths relative to the current
working directory, not to the snapshot's location.

### `contract.duplicate_key`

```json
{"detail": "Duplicate JSON key: snapshot_id", "error_code": "contract.duplicate_key", "invalid_params": [{"name": "snapshot_id", "reason": "duplicate key"}]}
```

Raised when a document contains the same object key twice. Most JSON libraries
silently keep the last occurrence; this one refuses, because the two readings
would hash differently.

### `contract.payload_too_large`

```json
{"detail": "big.snapshot.json exceeds 1 MiB.", "error_code": "contract.payload_too_large"}
```

One mebibyte of decoded JSON per document, checked before parsing.

### `engine.*`

Any `engine.*` code — `engine.power_balance`, `engine.time_regression`,
`engine.battery_bounds`, `engine.component_rating` and the rest — is an
internal invariant failure. Exit code 3. The engine detected that its own
output would have violated a conservation or bounds rule and refused to emit
it. This is a bug in dc-twin, not in your input. Report it with the two input
files, per [SECURITY.md](../../SECURITY.md) or the issue tracker.

## Server problems

### `server.non_loopback_host`

```json
{"detail": "The CLI binds to loopback only; use a hardened reverse proxy for deployment.", "error_code": "server.non_loopback_host"}
```

`dc-twin serve` accepts `127.0.0.1`, `localhost` or `::1` only. For anything
else use the container workflow in [OPERATIONS.md](../OPERATIONS.md).

### `server.invalid_port`

```json
{"detail": "Port must be from 1 through 65535.", "error_code": "server.invalid_port"}
```

## API problems

### `404 reference.scenario_not_found`

```json
{"detail": "No allowlisted synthetic scenario is named 'NOT-A-SCENARIO'.", "error_code": "reference.scenario_not_found", "status": 404, "request_id": "40d01a4f-fd01-4fb1-a90d-bf7a0a6b6f4b"}
```

The API runs only the five bundled fixtures. It accepts no arbitrary topology
at all — this is a security boundary, not a missing feature. Use the CLI.

### `404 run.not_found`

```json
{"detail": "The requested run is not retained by this instance.", "error_code": "run.not_found", "status": 404}
```

The run ID is unknown, invalid, or was evicted from the in-memory adapter.
Memory-backed instances lose runs on restart; the public explorer instance
loses them when its machine stops. Re-run the scenario.

### `409 replay.input_unavailable`

The run exists but its immutable reference fixture is not present in the
current engine build. Usually an engine upgrade.

### A replay that reports `matches: false`

Exit code 5 from the CLI, or `"matches": false` from the API. This is evidence
of semantic drift and should fail a release gate. Check, in order:

1. **Engine version.** `GET /health/live` or any result's `engine_version`.
   Different versions are expected to produce different hashes.
2. **The inputs.** Compare `snapshot_hash` and `scenario_hash` against the
   stored result. A one-character edit to a label moves the hash.
3. **Neither.** If the version and both input hashes match and the computation
   hash does not, that is a genuine determinism defect. Report it.

## Problems with no error message

The hardest failures are the ones that produce a clean run. Three to check for
deliberately:

**A run with unserved energy and no alarms.** If the shortfall exists from
`0 ms`, no `load_unserved` alarm is ever raised, because the alarm requires a
transition. Chapter 14's trap topology serves 60% of its load for ten minutes
in complete silence. Always read `unserved_energy_mj` first.

**A permanently weak redundancy state.** If a topology you believe is redundant
reports `supported` in every segment, check the `path` tags. Only `A` and `B`
count toward a qualifying source path, and retagging a working 2N topology to
`shared` demotes it silently and forever.

**A battery draining on a healthy topology.** If a UPS depletes in a run whose
service ratio is 100%, the allocation preferred the battery over a live feed
because it sat closer to the load. Check `source_power_w` for `ups-*` keys in
segments where you expected utility supply. Chapter 5 explains the mechanism.

---

Previous: [19. What conclusions may be drawn, and what may not](19-conclusions.md) ·
Next: [21. Glossary](21-glossary.md)
