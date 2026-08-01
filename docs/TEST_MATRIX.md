# Test Matrix

## Quality objective

Tests must demonstrate more than happy-path execution. The release gate covers strict input handling, topology rejection, deterministic state transitions, exact energy accounting, replay, persistence, API behavior, deployment health, and public-data boundaries.

Normative values are integer watts, millijoules, milliseconds, and parts per million. Decimal kWh and percentage displays are not acceptance oracles.

## Automated matrix

| Area | Evidence | Required cases |
|---|---|---|
| Strict JSON | Unit tests | Duplicate keys, invalid UTF-8, malformed JSON, `NaN`/infinity, oversized payload, canonical Unicode |
| Snapshot contract | Unit and schema tests | Every component subtype; required fields; unknown fields; invalid IDs; wrong units/version/classification; bounds and uniqueness |
| Scenario contract | Unit and schema tests | Every event kind; status-kind agreement; atomic open/close; load step; horizon and resolution bounds; unknown fields |
| Topology | Unit tests | Broken references; self-edge; directed cycle; nonterminal load; initially paralleled ATS/STS; invalid redundancy member |
| Event semantics | Unit tests | Stable priority; ID tie-break; contradictory same-target event; unknown target; wrong target kind; transfer overlap; load above rating |
| Capacity allocator | Unit tests | Node and edge limits; multiple sources; bottleneck; unreachable load; stable adjacency/source order; priority and service-order allocation |
| UPS model | Unit tests | Pass-through; battery source eligibility; exact debit; low threshold; exact depletion split; no negative energy; no modeled recharge |
| Timeline | Unit tests | Half-open contiguous segments; event and resolution boundaries; causal IDs; state hashes; conservation invariants |
| Metrics | Unit tests | Exact demanded/served/unserved energy; round-half-up ratio; zero-demand ratio; interruption duration/count; extrema; worst redundancy state; stranded capacity |
| Determinism | Unit tests | Input key reordering; repeated run; replay; stable hash; run ID excluded; meaningful input or engine-version change detected |
| Reference fixtures | Acceptance tests | Healthy, generator success, and every composite value in `REFERENCE_SCENARIO.md` |
| API | HTTP tests | Route success; RFC-style problem response; unknown scenario/run; invalid body; result contract; telemetry CSV content type and headers |
| Persistence | PostgreSQL integration tests | Migration up; append and retrieve; rollback on failure; replay lineage; canonical payload round trip; readiness failure |
| Browser | Smoke and accessibility checks | Scenario listing; run state; timeline/alarms; empty/error state; JSON and CSV export; keyboard use; reduced motion; narrow viewport |
| Packaging | Build tests | Source and wheel build; metadata; `twine check`; installed-wheel CLI/API import smoke |
| Containers | Compose smoke | Build; migration; liveness; readiness; API-to-database path; non-root/runtime configuration where declared |
| Supply chain | CI checks | Dependency audit; pinned action revisions; secret scan; no unexpected tracked binaries or generated results |

## Independent reference assertions

The composite fixture must produce exactly:

| Assertion | Expected value |
|---|---:|
| Demanded energy | 960,000,000,000 mJ |
| Served energy | 908,800,000,000 mJ |
| Unserved energy | 51,200,000,000 mJ |
| Service ratio | 946,667 ppm |
| Interruption duration | 32,000 ms |
| Interruption count | 1 |
| Peak demand / served power | 1,600,000 W / 1,600,000 W |
| Minimum served power | 0 W |
| Peak stranded capacity | 1,600,000 W |
| UPS A low-energy boundary | 336,000 ms |
| UPS A depletion boundary | 390,000 ms |
| Service restoration boundary | 422,000 ms |

Tests must also assert, for every segment:

```text
demand_w = served_w + unserved_w
demanded_energy_mj = served_energy_mj + unserved_energy_mj
battery_energy_mj >= 0
connection_flow_w <= connection_capacity_w
```

## Compatibility matrix

| Environment | Gate |
|---|---|
| Linux, Python 3.12 | Full format, lint, strict typing, unit/API tests, branch coverage, build, audit |
| Linux, Python 3.13 | Full format, lint, strict typing, unit/API tests, branch coverage |
| Windows, Python 3.13 | Focused import, contract, reference, CLI, and path-handling smoke |
| PostgreSQL service | Migration and repository integration suite |
| Container runtime | Image build and health/API smoke |

## Release gates

A release candidate is acceptable only when:

- formatting and lint checks have no differences or warnings;
- strict type checking passes;
- all unit, API, reference, and required integration tests pass without unexpected skips;
- branch coverage is at least 90%;
- package and container smoke tests pass;
- dependency audit reports no known unaccepted vulnerability;
- schema examples validate and independently calculated metrics match exactly;
- replay hashes are stable across supported Python versions and operating systems; and
- documentation, changelog, threat model, provenance, and limitations match the shipped behavior.

Coverage is a diagnostic, not a substitute for the failure-path and invariant evidence above.

## Manual release review

Before publication, review the complete tracked-file list and diff for secrets, personal data, customer data, proprietary materials, generated results, and misleading claims. Exercise the UI at desktop and narrow widths, inspect browser console and network failures, verify every documented command, and confirm that the API cannot be mistaken for an equipment-control surface.
