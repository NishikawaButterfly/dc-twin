# 21. Glossary

Terms as **this model** uses them. Where a term also has an industry meaning,
the entry says how the two differ, because that gap is where misreadings start.

---

**Alarm.** A timestamped annotation on the timeline, one of six codes. Raised
by an event or a derived milestone; recorded in the `alarms` array. Clears are
recorded separately, in `transitions[].alarms_cleared`. An alarm changes
nothing — it sheds no load, initiates no transfer, and has no operator,
acknowledgement or delivery mechanism.

**Atomic transfer.** An event that changes any number of connection positions
as one indivisible state transition, after which service is evaluated once.
"Atomic" refers to event ordering, not to transfer time — every transfer takes
zero milliseconds. It is a declaration of state, not a command to equipment.

**Autonomy.** Not a field. The time a UPS can carry its current draw, computed
as `stored_energy_mj / discharge_w`. You compute it from a segment; no metric
reports it.

**Availability (component).** One of `available`, `failed`, `maintenance`. The
solver distinguishes only `available` from the other two. Nothing to do with
availability as a reliability figure.

**Battery source.** A UPS that has become a finite source because no non-battery
source can energise it upstream, its own state is `available`, and its stored
energy is positive. A UPS that is upstream-energised is a pass-through node
contributing no battery capacity.

**`battery_backed`.** Redundancy state meaning a battery is required to serve
total demand and no non-battery path could do it alone. The load is fully
served. It is the only state with an implicit clock.

**Canonical JSON.** UTF-8, recursively sorted keys, no optional whitespace,
preserved Unicode, no non-finite values. All three hashes are SHA-256 digests
of canonical forms.

**Capacity (`capacity_w`).** An integer ceiling on watts through a component or
connection. Not a nameplate, not a thermal rating, not kVA, not derated,
without short-time overload. Enforced absolutely in every interval.

**Component.** A node in the directed graph. Nine kinds exist; only `utility`,
`generator`, `ups`, `ats`/`sts` and `load` change engine behaviour.
`switchgear`, `transformer` and `pdu` are behaviourally identical rated
pass-throughs.

**Computation hash.** SHA-256 of the deterministic semantic result, excluding
`run_id` and the hash field. Covers metrics, timeline, transitions, alarms,
telemetry and explanations — so it moves when the reporting resolution changes,
even though no metric does.

**Connection.** A directed edge with an integer rating and an open/closed
position. Not a cable or a breaker; no impedance, length or voltage drop.

**`connection_flow_w`.** Per-connection flow for an interval, from a maximum-flow
solution. A *feasible* allocation, not a predicted current. Presence in the map
means the edge was closed with both endpoints available; a value of zero means
available and idle; absence means open or an endpoint out.

**Demand (`demand_w`).** Constant power a load requests within an interval,
changed only by `load_step`. Not a load profile, no diversity, no inrush.

**Demanded energy.** `Σ (demand_w × duration_ms)` over the horizon. Depends on
the horizon you chose.

**Design snapshot.** The topology document: components, connections, ratings,
initial states, redundancy groups, provenance, assumptions.

**Determinism.** Same canonical inputs and engine version produce the same
computation hash, always. Not accuracy — a wrong input reproduces exactly.

**Eligible source.** An available utility, a running generator, or a qualifying
battery UPS. All are pooled into one source set with no preference between
battery and non-battery.

**Engine version.** Reported by `/health/live` and in every result. Hashes are
only comparable within one version. The runs in this guide are `1.0.0`.

**Event.** A timestamped state change, one of eight kinds. Events at the same
timestamp execute by semantic priority then event ID, and JSON array order is
irrelevant.

**Explanations.** A result block giving, for five metrics, the formula, input
references, causal event references and a one-line interpretation.

**Horizon (`horizon_ms`).** The scenario's total duration, 1 ms to seven days.
A hard boundary: nothing is simulated past it and every event must fall inside
it. Every energy metric is an integral over it.

**Interruption count.** Increments on each transition from full service to any
under-service. A run that *begins* under-served counts as 1 without anything
having been interrupted.

**Interruption duration.** Total duration of segments with **any** unserved
demand. Not the duration of a total loss — a single starved low-priority load
produces the same reading as a blackout.

**Load.** A terminal node with `demand_w`, `priority` and `service_order`. Not
an IT workload; `priority` is a sort key, not a criticality classification.

**`load_unserved`.** A `critical` alarm raised when total unserved power goes
from zero to positive. **Requires a transition**, so a run that is under-served
from the first millisecond never raises it.

**Maintenance.** A component availability value. Behaviourally identical to
`failed` inside the solver; the difference is the alarm code, its `info`
severity, and the event kinds that set and clear it.

**Millijoule (`mJ`).** The energy unit. `1 kWh = 3,600,000,000 mJ`. Because one
watt-millisecond is one millijoule, `energy_mj = power_w × duration_ms` is exact
integer arithmetic with no floating point anywhere in the kernel.

**Modeled redundancy state.** The run-level metric: the **worst** state observed
over any non-zero duration. A floor, not a summary — it can describe one second
of a ten-minute run.

**`no_demand`.** State when current demand is zero, so service-path evidence
does not apply. Ignored in the run-level worst state unless every segment has
zero demand.

**`no_path`.** State when served power is zero.

**`partial_service`.** State when served power is positive and below demand.
Given the sequential allocation policy, this usually means some loads are at
zero rather than all loads at reduced power.

**`path`.** A component tag accepting only `A`, `B` or `shared`. Feeds the
redundancy evidence calculation: only sources tagged `A` or `B` can qualify.
Not cosmetic — retagging a 2N topology to `shared` demotes it to `supported`
permanently.

**`ppm`.** Parts per million. The service ratio's unit; 1,000,000 ppm is 100%.

**Priority.** Integer 1–100 on a load, ascending. With `service_order` and
`component_id` it fixes the order in which loads are allocated capacity. Loads
are served completely in order; there is no proportional sharing.

**Redundancy evidence.** A separate hypothetical full-demand allocation per
eligible non-battery source, preserving current upstream state and ratings, and
hypothetically closing that path's own eligible load-input connections. It
describes what a path *could* do, not where power actually came from.

**Redundancy group.** A declarative block naming a mode (`N`, `N_PLUS_1`,
`TWO_N`) and members. Recorded, hashed, and completely ignored by the solver.
Design intent, not evidence, and the engine never flags a disagreement between
the two.

**Replay.** Recomputing from the same inputs and comparing computation hashes.
A mismatch exits 5 and is never coerced to success. It verifies the software,
not the inputs.

**Resolution (`resolution_ms`).** How finely the timeline is cut into reported
segments. Does **not** affect accuracy: events, derived UPS milestones and the
horizon always produce their own boundaries. Changing it changes the segment
count and the computation hash while leaving every metric identical.

**Result.** A single JSON document with 14 top-level fields, including the
timeline, transitions, alarms, telemetry, metrics, explanations and three
hashes.

**Run ID.** `run-` plus the first 16 hex characters of the computation hash. A
locator, not a credential.

**Scenario.** A horizon, a resolution and a list of events, bound to one
snapshot by `snapshot_id`.

**Segment.** A half-open interval `[start_ms, end_ms)` over which every modelled
quantity is constant. Power and flow apply throughout; `battery_energy_mj` and
`state_hash` describe the state **at `end_ms`**.

**Served energy.** `Σ (served_w × duration_ms)`.

**Service ratio (`service_ratio_ppm`).** Served energy over demanded energy for
one scenario, in ppm, by integer round-half-up. Defined as 1,000,000 ppm when
demand is zero. **Not availability, not uptime, not an SLA.** Reducing demand
improves it.

**`single_path`.** State when exactly one qualifying source path could serve
total demand alone. Reported both by a healthy single-path design and by a
redundant design that has lost a path — the two are indistinguishable from the
value.

**`source_power_w`.** Per-source delivered power for an interval. Eligible
sources appear here at `0 W`, so presence means eligible, not supplying. The
only reliable indicator that a battery is discharging is a `ups-*` key with a
positive value.

**Stranded capacity.** `min(unserved_w, unused_available_source_capacity_w)`,
nonzero only while demand is unserved. An isolation indicator. **Not** spare
capacity, margin, firm capacity, reserve, or a claim that a switch can safely be
closed. Zero can mean fully served, fully committed, or nothing left.

**State hash.** SHA-256 of canonical runtime state at a segment's `end_ms`:
statuses, connection positions, running generators, demands, battery energies,
latched alarms. Excludes ratings, kinds and labels.

**`supported`.** State when non-battery capacity fully serves demand but the
graph proves neither `two_n` nor `single_path`. On a topology you believe is
redundant, usually a symptom of `path` tags set to `shared`.

**Synthetic.** The only accepted `data_classification`. A policy gate, enforced
by the parser on every snapshot and scenario.

**Telemetry.** A protocol-neutral point stream derived arithmetically from each
segment's end state. Every point carries `quality=synthetic`. Never a
measurement; no Modbus, no polling, no device addressing. Exportable as CSV
from the API only.

**Timeline.** The ordered list of segments. The primary output; metrics are
integrals over it and the computation hash covers it.

**Transition.** A record of one state change with sequence number, timestamp,
causal event, target, before and after state hashes, and the alarms raised and
cleared. The shortest useful summary of any run.

**`two_n`.** State when at least two distinct source paths tagged `A` and `B`
could each serve total demand alone. **Not** a Tier rating and not a statement
about single points of failure: a topology whose two paths converge on one
shared component reports `two_n` right up to the instant that component fails.

**Unserved energy.** `Σ (unserved_w × duration_ms)`. Counts watts of undelivered
demand and milliseconds. Counts no consequence, nothing outside the horizon, no
demand you did not declare, and does not distinguish which load was lost.

**UPS usable energy (`usable_energy_mj`).** Initially stored energy. A bucket of
joules: no chemistry, no aging, no temperature, no discharge-rate derating, no
recharge. Autonomy scales exactly inversely with draw. The most consequential
input in most runs.

---

Previous: [20. Troubleshooting](20-troubleshooting.md) ·
[Back to the index](README.md)
