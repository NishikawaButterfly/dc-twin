# ADR 0001: Build a deterministic active-power capacity simulator

- Status: Accepted
- Date: 2026-08-01
- Decision owners: Project maintainers

## Context

The portfolio needs an auditable way to explore how a synthetic data-center electrical architecture responds to failure, maintenance, restoration, transfer, generator, and load events. The result must be reproducible, explainable, small enough to review, and honest about its engineering limits.

Calling a simplified graph model a power-flow or protection tool would be misleading. Implementing a validated AC solver, short-circuit model, protection-coordination engine, transient simulation, or equipment-control interface would require materially different data, equations, verification, qualified review, and safety governance.

Floating-point time and energy integration would also make reference boundaries and cross-platform replay harder to audit than the use case requires.

## Decision

Build a deterministic, synchronous active-power capacity simulator with these constraints:

- directed acyclic topology;
- component-node and connection-edge capacity limits;
- integral maximum-flow allocation with stable ID ordering;
- sequential load service by explicit priority and service order;
- integer watts, millijoules, milliseconds, and parts per million;
- explicit, deterministically ordered state-change events;
- finite UPS energy with exact threshold and depletion boundaries;
- scenario-level timelines, transitions, alarms, synthetic telemetry, explanations, and hashes; and
- fail-closed contract, topology, and invariant validation.

The model will repeatedly state that it is not AC power flow, protection analysis, equipment certification, a safety study, a compliance assessment, or a control system.

## Consequences

### Positive

- Reference outcomes can be calculated independently with exact integer arithmetic.
- Identical canonical inputs and engine version can be replayed to the same semantic hash.
- Capacity bottlenecks, unserved demand, battery duration, and isolated source capacity are explainable from a compact state timeline.
- The domain kernel can be tested without HTTP, a browser, or a database.
- Invalid graphs fail before producing plausible-looking output.

### Negative

- The model cannot answer voltage, current, reactive-power, fault, selectivity, transient, thermal, fuel, efficiency, or regulatory questions.
- A DAG excludes looped distribution and network reconfiguration that would require a richer graph/state model.
- Sequential priority allocation is intentionally policy-driven and is not a globally fair or economic optimum.
- UPS behavior is an idealized energy store/pass-through abstraction.
- Synchronous bounded execution limits topology size and scenario horizon.

## Alternatives considered

### Use an AC power-system library

Rejected for this release. A library call would not make sparse synthetic inputs sufficient for valid engineering conclusions, and the required verification and professional-governance scope is far larger.

### Use a generic discrete-event framework

Rejected for the core. It would add scheduling surface area without removing the need to specify exact same-time ordering, capacity allocation, battery boundaries, and hashing. The bounded event loop remains purpose-built and reviewable.

### Use floating-point SI or engineering units

Rejected for normative calculations. Decimal kW/kWh values remain a presentation concern; integer base units make the energy identity exact and reference evidence portable.

### Start with a probabilistic availability model

Rejected. The initial requirement is deterministic replay of named events. Future seeded Monte Carlo orchestration may call the deterministic kernel, but it must not obscure the reference equations.

## Verification

The decision is enforced by versioned schemas, topology rejection tests, exact reference calculations, capacity and energy invariants, replay hashes, branch coverage, and explicit public limitations. Any future circuit solver or live-control function requires a separate ADR and safety boundary, not an incremental label change.
