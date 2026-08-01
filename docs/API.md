# API Reference

## Scope

The API runs only the allowlisted synthetic fixtures shipped with the application. It does not accept arbitrary facility topologies, ingest telemetry, or expose an equipment-control route. All modeled results are deterministic active-power capacity results, not AC power-flow, protection, safety, control, or certification outputs.

The OpenAPI document is served at `/api/v1/openapi.json` and interactive documentation at `/api/docs`.

## Conventions

- JSON requests and responses use UTF-8 and snake_case field names.
- Normative values use integer watts, millijoules, milliseconds, and parts per million.
- Successful JSON responses use `application/json`.
- Errors use `application/problem+json` in the RFC 9457 Problem Details shape.
- Every response carries `X-Request-ID`. A valid client-supplied `X-Request-ID` is echoed; otherwise the server creates one.
- `run_id` is content-addressed as `run-` plus the first 16 hexadecimal characters of the computation hash in version 0.1.0.

## Reference-scenario catalog

### `GET /api/v1/reference-scenarios`

Returns the allowlisted synthetic scenarios available in this engine build.

Response: `200 OK`

```json
{
  "engine_version": "0.1.0",
  "data_classification": "synthetic",
  "disclaimer": "Deterministic active-power capacity simulation; not AC power flow, protection, safety, control, or certification.",
  "scenarios": [
    {
      "scenario_id": "REF-DC-2N-001",
      "label": "PDU B maintenance, utility A loss, generator failure, and path B restoration",
      "description": "Composite maintenance, utility loss, generator-start failure, UPS depletion, and service restoration.",
      "modeled_redundancy": "event_dependent",
      "horizon_ms": 600000,
      "event_count": 6,
      "data_classification": "synthetic"
    },
    {
      "scenario_id": "REF-DC-2N-GEN-SUCCESS",
      "label": "PDU B maintenance with utility A loss and successful generator A transfer",
      "description": "Planned path maintenance followed by utility loss, UPS bridge, and successful generator start.",
      "modeled_redundancy": "event_dependent",
      "horizon_ms": 600000,
      "event_count": 5,
      "data_classification": "synthetic"
    },
    {
      "scenario_id": "REF-DC-2N-HEALTHY",
      "label": "Healthy 2N reference operation",
      "description": "Healthy two-path reference operation with no injected events.",
      "modeled_redundancy": "two_n",
      "horizon_ms": 600000,
      "event_count": 0,
      "data_classification": "synthetic"
    }
  ]
}
```

Catalog metadata is descriptive. `modeled_redundancy` is not a Tier, code, or engineering-compliance classification.

## Create or retrieve a deterministic run

### `POST /api/v1/reference-scenarios/{scenario_id}/runs`

Runs the named allowlisted fixture. The request has no body. The same fixture and engine version produce the same computation hash and content-addressed run ID.

Response: `200 OK` with a complete [`SimulationResult` v1](../contracts/result/v1/schema.json).

| Top-level field | Meaning |
|---|---|
| `schema_id`, `schema_version`, `engine_version` | Exact interpretation boundary |
| `run_id` | Content-addressed run locator |
| `snapshot_hash`, `scenario_hash`, `computation_hash` | Canonical provenance and replay evidence |
| `scenario` | Scenario identity, label, and horizon |
| `metrics` | Exact integrated energy, service, interruption, extrema, stranded capacity, and worst modeled state |
| `timeline` | Half-open constant-state segments with flows, battery energy, causal events, and state hashes |
| `transitions`, `alarms` | External and derived state evidence |
| `telemetry` | Deterministically derived points, each marked synthetic |
| `explanations` | Formula, input, event, and interpretation links for key metrics |

Errors:

- `404 reference.scenario_not_found` when the identifier is not allowlisted.
- `413` for a bounded-resource violation discovered during execution.
- `422` for a contract, topology, or invariant rejection.

## Retrieve a retained run

### `GET /api/v1/runs/{run_id}`

Returns the exact retained result payload.

Responses:

- `200 OK` with a complete `SimulationResult` v1.
- `404 run.not_found` when the identifier is invalid, unknown, evicted from the memory adapter, or absent from the configured PostgreSQL store.

Run IDs are locators, not authorization credentials. The reference API has no user authorization and must not be exposed to an untrusted network.

## Verify deterministic replay

### `POST /api/v1/runs/{run_id}/replay`

Recomputes the bundled snapshot and scenario associated with the retained run and compares the resulting semantic hash. The request has no body. Replay does not mutate the original record or insert a replacement.

Response: `200 OK`

```json
{
  "run_id": "run-0123456789abcdef",
  "expected_computation_hash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "actual_computation_hash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "matches": true,
  "replay_run_id": "run-0123456789abcdef"
}
```

Responses:

- `404 run.not_found` when the original run is not retained.
- `409 replay.input_unavailable` when the run exists but its immutable reference fixture is unavailable in the current engine build.

A `matches=false` response is evidence of semantic drift and should fail a release or operational verification. It is never silently coerced to success.

## Export synthetic telemetry

### `GET /api/v1/runs/{run_id}/telemetry.csv`

Returns deterministic telemetry derived from the retained timeline.

Response: `200 OK`, `text/csv; charset=utf-8`, with attachment name `{run_id}-telemetry.csv`.

The header is stable:

```csv
sequence,time_ms,component_id,metric,value,unit,quality,state_hash
```

Every row has `quality=synthetic`. The point series is SCADA-style but protocol-neutral; it is not a Modbus capture or live measurement. A string beginning with a spreadsheet formula-control character is prefixed with an apostrophe during CSV serialization. The JSON result remains the authoritative typed representation.

Returns `404 run.not_found` when the run is not retained.

## Health endpoints

### `GET /health/live`

Process-level health. It does not test PostgreSQL.

```json
{"status":"live","engine_version":"0.1.0"}
```

### `GET /health/ready`

Dependency readiness. The memory adapter is immediately ready; the PostgreSQL adapter executes a minimal database query.

- `200 OK`: `{"status":"ready","engine_version":"0.1.0"}`
- `503 Service Unavailable`: `{"status":"not_ready"}`

## Problem Details

An error response has this shape:

```json
{
  "type": "https://github.com/NishikawaButterfly/dc-twin/blob/main/docs/API.md#problem-details",
  "title": "Simulation run not found",
  "status": 404,
  "detail": "The requested run is not retained by this instance.",
  "instance": "/api/v1/runs/run-0000000000000000",
  "error_code": "run.not_found",
  "request_id": "f58a7c06-7b30-4cf4-b67b-8c6b77157e91"
}
```

Validation errors may add:

```json
{
  "invalid_params": [
    {"name": "path.to.field", "reason": "must be a positive integer"}
  ]
}
```

Stable public error-code families are:

| Family | Meaning |
|---|---|
| `api.*` | HTTP request validation |
| `contract.*` | JSON shape, unit, version, identifier, or resource-limit rejection |
| `topology.*` | Unsupported or impossible graph structure |
| `scenario.*` | Invalid event target, state, reference, or limit |
| `engine.*` | Internal invariant failure |
| `reference.*` | Allowlisted fixture lookup failure |
| `run.*` | Retained-run lookup failure |
| `replay.*` | Replay precondition failure |

Clients should branch on `status` and `error_code`, log `request_id`, and display `detail` as untrusted text. They must not parse human wording as a protocol.

## Result contracts

- [Electrical Design Snapshot v1](../contracts/electrical-design-snapshot/v1/schema.json)
- [Scenario v1](../contracts/scenario/v1/schema.json)
- [Simulation Result v1](../contracts/result/v1/schema.json)
- [Model semantics and limitations](MODEL_SPECIFICATION.md)
