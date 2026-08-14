# 2. Model concepts

Four nouns carry the whole model: component, connection, capacity and load.
Each one means less than the equivalent word means in electrical engineering,
and the gap is where misreadings start. This chapter states what each one is
and, more usefully, what it deliberately is not.

The normative definitions live in
[MODEL_SPECIFICATION.md](../MODEL_SPECIFICATION.md) sections 3 and 4. This
chapter is the working explanation.

## The graph

A design snapshot is a directed acyclic graph. Nodes are components, edges are
connections. Power enters at source components and leaves at load components,
and every intermediate component is a pipe with a width.

That is the entire physical model. There is no voltage level, no phase, no
neutral, no earth, no impedance, and no direction of current other than the
direction you drew the edge. If you draw an edge from a PDU to a UPS, power
flows that way, because you said so.

Version 1 rejects cycles outright:

```powershell
dc-twin validate-design bad/cycle.snapshot.json
```

```json
{"detail": "Directed cycle detected at pdu-a; v1 supports DAG topologies only.", "error_code": "topology.cycle_not_supported"}
```

This matters more than it first appears. Real distribution has loops: ring
buses, tie breakers between switchboards, bus-coupled arrangements where power
can arrive from either side. dc-twin cannot represent any of them directly. You
model a tie as a pair of directed edges in one chosen direction and accept that
the model will not consider flow the other way.

## Component

A component is a node with an identifier, a human label, a `kind`, a `path`
tag, an integer `capacity_w`, and an availability state.

Nine kinds exist: `utility`, `generator`, `switchgear`, `transformer`, `ups`,
`ats`, `sts`, `pdu`, `load`.

Only four of those kinds change how the engine behaves:

| Kind | Special behaviour |
|---|---|
| `utility` | Eligible source whenever its state is `available` |
| `generator` | Eligible source only after a `generator_running` event, and only with `start_delay_ms` respected |
| `ups` | Can become a finite battery source; carries `usable_energy_mj` and `low_energy_threshold_pct` |
| `ats` / `sts` | Subject to the paralleling guard: never more than one closed input |
| `load` | Terminal; carries `demand_w`, `priority`, `service_order` |

`switchgear`, `transformer` and `pdu` are behaviourally identical. Each is a
node with a rating that passes power through. A transformer in this model does
not transform anything: it has no turns ratio, no impedance, no losses, no
inrush, no tap.

This is easy to demonstrate. Take the bundled `reference-2n` snapshot, change
every `"kind": "transformer"` to `"kind": "switchgear"`, leave every rating and
connection untouched, and re-run the composite scenario. Comparing the two
result files field by field:

```text
computation hash equal : False
metrics equal          : True
timeline (minus hashes): True
alarms equal           : True
state hashes equal     : True
```

Every watt, every flow, every alarm and every per-segment state hash is
identical. Only the top-level computation hash moves, because the canonical
snapshot JSON changed. The component kind had no effect on the physics because,
for these three kinds, there is no physics attached to it.

That is worth stating plainly because component kind reads like a model of
equipment behaviour and mostly is not. It is a label, plus five special cases.

### What a component deliberately does not mean

- It is not a physical device. It is a capacity constraint with a name.
- Its `capacity_w` is not a nameplate rating, a thermal limit, or a continuous
  duty rating. It is the maximum integer watts the engine will route through
  the node. Nothing derates it, nothing overloads it, and nothing fails from
  running at 100% of it forever.
- Its availability state is not a condition assessment. `available`, `failed`
  and `maintenance` are three words with exactly two meanings to the engine:
  `available` carries flow, the other two do not.

That last point is worth pausing on. `failed` and `maintenance` are
behaviourally identical inside the capacity solver. The difference is entirely
in the alarm severity raised (`critical` versus `info`) and in the event kinds
that set and clear them. A component in maintenance is not "safely isolated"
and a component that failed is not "damaged". Both are just out of the graph.

### The `path` tag

Every component carries a `path` value, and it accepts exactly three strings:

```powershell
dc-twin validate-design guide-3feed.snapshot.json
```

```json
{"detail": "Invalid value at $.components[0].path: must be A, B, or shared", "error_code": "contract.invalid_field", "invalid_params": [{"name": "$.components[0].path", "reason": "must be A, B, or shared"}]}
```

`A`, `B`, or `shared`. This is not cosmetic metadata. It feeds the redundancy
evidence calculation, and mislabelling it silently changes the state the engine
reports for an otherwise identical topology. Chapter 5 demonstrates that with
two runs. Two consequences follow immediately:

- The model cannot express a third independent source path. There is no `C`.
  Three-feed arrangements, distributed-redundant and block-redundant
  ("catcher") topologies cannot be labelled in a way the redundancy evidence
  understands.
- `shared` is not a neutral default. A component tagged `shared` never counts
  toward a qualifying source path.

## Connection

A connection is a directed edge with an identifier, a `from_component`, a
`to_component`, an integer `capacity_w`, and an `initial_closed` boolean.

Closed means the edge exists for flow. Open means it does not. There is no
intermediate state, no racked-out position, no interlock, and no transition
time. A connection changes state instantaneously when an `atomic_transfer`
event says so.

### What a connection deliberately does not mean

- It is not a cable, a busway or a breaker. It has no length, no impedance and
  no voltage drop.
- Its `capacity_w` is not an ampacity. It is an integer ceiling on flow.
- "Closed" is not "energised" and it is not "safe". A closed connection between
  two available components lets the solver route power. Whether closing that
  device in a real facility would parallel two sources out of phase, exceed a
  fault duty, or violate a switching procedure is entirely outside the model.
  The one exception is the ATS/STS paralleling guard in chapter 8, and it is a
  contract check, not an engineering safety analysis.

## Capacity

Capacity is an integer number of watts, and it appears in three places:
component ratings, connection ratings, and load demand.

The engine enforces exactly this, per segment, and asserts it internally:

```text
0 <= connection_flow_w[id] <= connection.capacity_w
0 <= component_throughput_w[id] <= component.capacity_w
```

Capacity is enforced as a hard, instantaneous ceiling. Nothing runs at 110% for
ten seconds. Nothing has a short-time rating. Nothing has an overload curve.
When demand exceeds what capacity can deliver, the surplus is simply unserved.

### What capacity deliberately does not mean

- It is not apparent power. There is no power factor and no distinction between
  kW and kVA. A "2 MW UPS" in a snapshot means 2,000,000 W of throughput, and
  the model has no opinion on what that would be in kVA.
- It is not efficiency-adjusted. The model is lossless. One watt in is one watt
  out, through transformers, UPS units and every other node. A path that
  delivers 1.6 MW to loads draws exactly 1.6 MW from its source.
- It is not a design margin. Spare capacity is not reported anywhere as a
  metric. The only figure that looks like spare capacity is stranded capacity,
  and chapter 14 explains why it is not that.

## Load

A load is a terminal node with three extra fields: `demand_w`, `priority` and
`service_order`. Loads may not have outgoing connections:

```powershell
dc-twin validate-design bad/nonterminal.snapshot.json
```

```json
{"detail": "Load it-load-1 must be a terminal node.", "error_code": "topology.load_not_terminal"}
```

A load's `demand_w` is a constant within any interval and changes only when a
`load_step` event changes it. `priority` (1 to 100) and `service_order`
(1 to 10,000) determine the order in which loads are considered when capacity
is short. Chapter 4 covers the allocation policy.

### What a load deliberately does not mean

- It is not an IT workload. There is no utilisation curve, no diversity factor,
  no ramp, no inrush and no startup surge. Demand is a step function you author.
- It is not a criticality classification. `priority` is a sort key. Priority 1
  does not mean "life safety" to the engine; it means "considered first".
- A dual-cord load is not modelled as a device with two inputs that share.
  It is a node with two incoming edges, and the solver may put all the flow on
  one of them. Chapter 11 shows a run where exactly that happens.

## Units and arithmetic

Normative arithmetic is integer, and the identity is exact:

```text
energy_mj = power_w * duration_ms
```

because one watt-millisecond is one millijoule. No floating point is used for
energy accounting anywhere in the kernel. This is why hand calculation works as
an acceptance oracle: `432,000,000,000 mJ / 1,600,000 W = 270,000 ms` exactly,
with no rounding to argue about.

Kilowatt-hours appear only in documentation and in the web explorer, converted
at `1 kWh = 3,600,000,000 mJ`. When this guide writes "14.22 kWh" the exact
value is 51,200,000,000 mJ, and the exact value is the one to quote.

## What the model has no concept of at all

For completeness, and because this list is what you will need when someone asks
whether dc-twin can answer their question. None of the following exists
anywhere in version 1:

Voltage, current, phase, frequency, reactive power, power factor, harmonics,
inrush, impedance, voltage drop, fault current, short-circuit duty,
selectivity, relay coordination, breaker curves, arc flash, grounding, thermal
behaviour, cooling, fuel, generator dynamics, battery chemistry, battery aging,
recharge, UPS efficiency or conversion losses, bypass ratings distinct from
component capacity, communications latency, mechanical systems, probabilistic
reliability, common-cause failure, human procedure, cost, or regulatory rules.

If the question you are trying to answer needs any of those, dc-twin cannot
answer it, and no combination of runs will make it able to.

---

Previous: [1. Introduction](01-introduction.md) ·
Next: [3. Building a topology](03-building-a-topology.md)
