# Model Specification

## 1. Scope and normative language

This document specifies version 1 of the deterministic active-power capacity model. The terms **must**, **must not**, **should**, and **may** describe requirements on the implementation.

The model answers one bounded question: given a directed synthetic topology, component and connection capacities, load demand, finite UPS energy, and timestamped state changes, how much demand can be served during each modeled interval?

It does not solve electrical circuit equations and must not be used for design approval, switching instructions, protection settings, safety studies, certification, or regulatory compliance.

## 2. Units and arithmetic

Inputs and normative results use integers:

| Quantity | Unit | Symbol |
|---|---:|---:|
| Active power | watt | `W` |
| Energy | millijoule | `mJ` |
| Time | millisecond | `ms` |
| Ratio | parts per million | `ppm` |

For constant active power over an interval, the numeric identity is exact:

```text
energy_mj = power_w * duration_ms
```

This follows because one watt-millisecond equals one millijoule. Binary floating-point is not used for normative energy accounting. Human-readable kWh values in documentation and the UI are presentation conversions only, using `1 kWh = 3,600,000,000 mJ`.

## 3. Input model

### 3.1 Topology

The snapshot defines a directed graph `G = (V, E)`:

- `V` contains utilities, generators, switchgear, transformers, UPS units, ATS units, STS units, PDUs, and terminal loads.
- Every component has a positive active-power capacity and an initial availability state.
- Every connection has a positive capacity and an initial open or closed state.
- Loads additionally define demand, priority, and deterministic service order.
- UPS units additionally define initially usable energy and a low-energy threshold.
- Generators additionally define a minimum modeled start delay.

Version 1 supports directed acyclic graphs only. Component IDs, connection IDs, event IDs, and scenario IDs must be unique in their respective scopes. Every reference must resolve. A load must be terminal. An ATS or STS must not have more than one initially closed input because source paralleling is not modeled.

Redundancy groups are descriptive design intent. They do not increase capacity and cannot override graph reachability or state.

### 3.2 Source eligibility

A utility is an eligible non-battery source while its component state is `available`.

A generator is an eligible non-battery source only when its component state is `available` and a `generator_running` event has established its running state. An available standby generator is not implicitly energized.

Version 1 models reactive starts only. Every `generator_running` or `generator_start_failure` outcome must have a preceding `component_failure` for a utility on the same A or B path. The outcome must occur no earlier than the generator's `start_delay_ms` after the latest such preceding loss. Proactive starts without source loss and early outcomes are rejected as `scenario.generator_without_source_loss` and `scenario.generator_start_too_early`, respectively.

A UPS passes upstream power while an available utility or running generator can energize it through the current closed, available graph. A UPS becomes a finite battery source only when no such non-battery source can energize it upstream, its own state is `available`, and its stored energy is positive. Version 1 does not model charging, conversion losses, bypass ratings distinct from component capacity, or battery degradation.

### 3.3 Scenarios

A scenario has a positive horizon, a positive output resolution no greater than the horizon, and zero or more events. Events at the same time are ordered by semantic priority and then by event ID:

| Priority | Event kinds |
|---:|---|
| 10 | `component_failure`, `generator_start_failure` |
| 20 | `maintenance_start` |
| 30 | `component_restore`, `maintenance_end` |
| 35 | `generator_running` |
| 40 | `atomic_transfer` |
| 50 | `load_step` |

This ordering applies independently of JSON array order. Multiple component events targeting the same component at the same timestamp are rejected as contradictory.

An atomic transfer applies all listed opens and closes as one state transition. The same connection cannot appear in both lists. The event describes a scenario state change; it is not a command to physical equipment.

## 4. Capacity allocation

### 4.1 Available network

For each interval, unavailable components and open connections are excluded. Component capacities are enforced by deterministic node splitting; connection capacities are enforced on directed edges. Eligible sources connect to a conceptual super-source.

Loads are considered in ascending `(priority, service_order, component_id)` order. For each load, an integral maximum-flow calculation allocates as much of its current demand as possible from the remaining network capacity. Source IDs and adjacency lists are sorted before traversal so an otherwise equivalent graph does not depend on dictionary, file-system, or database order.

This sequential policy is deliberate and auditable. It is not an economic dispatch, optimal power flow, proportional fairness algorithm, or prediction of protective-device behavior.

### 4.2 Interval boundaries

The simulation evaluates scheduled event times, requested resolution boundaries, the scenario horizon, and internally derived UPS low-energy and depletion times. A derived battery transition splits an interval at the exact integer millisecond boundary so that energy debit, alarms, and service changes remain traceable.

Within an interval, component state, connection state, load demand, and allocated power are constant. The model debits each discharging UPS by:

```text
battery_debit_mj = battery_output_w * interval_duration_ms
```

Stored energy must never become negative. When energy reaches zero, the kernel recomputes service for the remainder of the scenario.

## 5. State and outputs

### 5.1 Timeline

Each half-open segment `[start_ms, end_ms)` records demand, served and unserved power, stranded capacity, redundancy evidence, per-UPS energy, per-source power, per-load service, per-connection flow, causal event IDs, and a state hash. Power and flow values apply throughout the interval. `battery_energy_mj` and `state_hash` represent the state at `end_ms`, after the interval's exact energy debit and before any transition at that same boundary.

The following invariants must hold for every segment:

```text
0 <= served_w <= demand_w
unserved_w = demand_w - served_w
0 <= connection_flow_w[id] <= connection.capacity_w
0 <= component_throughput_w[id] <= component.capacity_w
battery_energy_mj[id] >= 0
```

### 5.2 Redundancy evidence

Redundancy evidence evaluates each distinct eligible non-battery source path with a separate deterministic full-demand allocation. The check preserves current upstream component state, connection state, component ratings, and connection ratings. Only eligible load-input transfer connections belonging to the same available A or B path are hypothetically closed for this evidence calculation. That hypothetical closure is not applied to the scenario state and is not a claim that an actual transfer is safe or automatic.

The timeline then reports modeled evidence, not an engineering certification:

- `two_n`: at least two distinct non-battery source paths can each serve total demand alone in the evaluated graph;
- `supported`: non-battery capacity fully serves demand, but the graph does not prove either `two_n` or `single_path` evidence;
- `single_path`: exactly one non-battery source path can serve total demand alone;
- `battery_backed`: battery supply is required to serve total demand and no non-battery path can do so alone;
- `partial_service`: served power is greater than zero but less than demand; and
- `no_path`: served power is zero; and
- `no_demand`: current demand is zero, so service-path evidence is not applicable.

The run-level `modeled_redundancy_state` is the worst non-zero-duration state observed under this order, from worst to strongest: `no_path`, `partial_service`, `battery_backed`, `single_path`, `supported`, `two_n`. `no_demand` is ignored unless every segment has zero demand. This is scenario evidence only; it does not establish N, N+1, or 2N compliance.

### 5.3 Stranded capacity

Stranded capacity is an isolation indicator and is nonzero only while demand is unserved:

```text
stranded_capacity_w = min(unserved_w, unused_available_source_capacity_w)
```

It highlights modeled source capacity that cannot reach unserved load because of topology, component state, connection state, or a downstream capacity constraint. It is not reserve margin, firm capacity, or a claim that a switch can safely be closed.

### 5.4 Aggregate metrics

Demanded, served, and unserved energy are exact sums over timeline segments. Interruption duration is the total duration of segments with unserved demand. Interruption count increments on each transition from full service to any under-service. Peak and minimum power metrics are extrema across nonempty segments.

`service_ratio_ppm` uses deterministic integer round-half-up arithmetic:

```text
service_ratio_ppm
  = (served_energy_mj * 1,000,000 + demanded_energy_mj // 2)
    // demanded_energy_mj
```

When demanded energy is zero, the ratio is defined as `1,000,000 ppm`.

### 5.5 Traceability and telemetry

Every transition records before and after state hashes and alarm changes. Every timeline segment records a state hash. Metric explanations identify formulas, input references, causal event references, and a concise interpretation.

Telemetry is a protocol-neutral, SCADA-style point stream deterministically derived from each segment's end state at `time_ms=end_ms`. It is synthetic, carries `quality=synthetic`, and is never evidence that a physical measurement occurred. Version 1 does not implement Modbus registers, packets, polling, device addressing, timestamp uncertainty, or a live SCADA connector.

## 6. Canonicalization and replay

Canonical JSON uses UTF-8, recursively sorted object keys, `,` and `:` separators without optional whitespace, preserved Unicode, and no non-finite values. Snapshot and scenario hashes are SHA-256 digests of their canonical JSON representations.

The computation hash covers the deterministic semantic result, excluding `run_id` and the computation-hash field. Given the same canonical inputs and engine version, replay must produce the same computation hash. A mismatch is surfaced; it is not silently accepted.

## 7. Rejection conditions

Version 1 applies these synchronous execution limits:

| Resource | Limit |
|---|---:|
| Decoded JSON payload | 1 MiB per file/request |
| Components | 250 |
| Connections | 500 |
| Redundancy groups | 100 |
| External events | 1,000 |
| Scenario horizon | 604,800,000 ms / 7 days |
| Timeline segments | 10,000 |
| State transitions | 10,000 |
| Synthetic telemetry points | 250,000 |

Before execution, the parser estimates the resolution, external-event, UPS-milestone, and telemetry envelope and rejects a scenario that cannot remain within these limits.

The simulator fails closed for, among other cases:

- unknown or additional contract fields;
- duplicate JSON keys or identifiers;
- unsupported schema versions or non-synthetic classification;
- non-integer, negative, out-of-range, or non-finite values;
- references to missing components or connections;
- directed cycles, self-connections, nonterminal loads, or initially paralleled ATS/STS inputs;
- load steps above the load rating;
- generator events aimed at non-generators;
- generator outcomes without a preceding same-path utility failure or before the declared start delay;
- events outside the scenario horizon; and
- payload, component, connection, event, horizon, or output sizes above documented limits.

An invalid model must never be coerced into a plausible-looking simulation.

## 8. Explicit limitations

Version 1 does **not** model voltage, current, phase, reactive power, power factor, frequency, harmonics, losses, inrush, transformer impedance, voltage drop, fault current, short-circuit duty, selectivity, relay coordination, breaker curves, arc flash, grounding, thermal behavior, fuel, generator dynamics, battery chemistry, battery aging, UPS efficiency, recharge, communications latency, mechanical systems, probabilistic reliability, common-cause failure, human procedure, or regulatory rules.

The outputs are not AC power-flow results, protection studies, equipment ratings, availability guarantees, certifications, operating instructions, or control signals. A qualified engineer must use appropriate validated tools and governed site data for real decisions.
