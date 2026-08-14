# 14. Stranded capacity

Stranded capacity is the most useful thing dc-twin reports that a drawing will
not tell you, and the most commonly misread. It is an isolation indicator. It
is not spare capacity.

## The definition

```text
stranded_capacity_w = min(unserved_w, unused_available_source_capacity_w)
```

evaluated per segment, and **nonzero only while demand is unserved**.

`unused_available_source_capacity_w` is the total rated capacity of every
currently eligible source, minus what those sources are actually delivering.
Eligible means available utilities, running generators, and UPS units that
qualify as battery sources under the chapter 6 rule.

The engine's explanation block:

```json
{
 "formula": "max(min(unserved_w, available_source_capacity_w - used_source_capacity_w))",
 "summary": "Capacity isolated from unmet load; this is not ordinary spare margin."
}
```

## The question it answers

> Right now, is there modelled source capacity that cannot reach load that is
> going unserved?

If yes, you have an isolation problem: capacity exists, demand exists, and the
graph does not connect them. If no, you have a capacity problem: there is
simply not enough source.

That distinction is the whole value of the metric, and it is exactly the
distinction a single-line diagram makes hard to see.

## A trap topology

Build one deliberately. Two 1.2 MW utilities feeding a 1 MW load, but:

- PDU A is rated **600,000 W** — below the load it serves;
- the cord from PDU B is `initial_closed: false` — a normally-open reserve.

```json
{ "id": "pdu-a", "kind": "pdu", "path": "A", "capacity_w": 600000, ... },
{ "id": "pdu-b", "kind": "pdu", "path": "B", "capacity_w": 1200000, ... },
{ "id": "it-load-1", "kind": "load", "demand_w": 1000000, ... }
```

```json
{ "id": "pdu-a-to-load-1", "from_component": "pdu-a", "to_component": "it-load-1",
  "capacity_w": 1000000, "initial_closed": true },
{ "id": "pdu-b-to-load-1", "from_component": "pdu-b", "to_component": "it-load-1",
  "capacity_w": 1000000, "initial_closed": false }
```

The snapshot declares `{"id": "source-pair", "mode": "TWO_N", "members":
["utility-a", "utility-b"]}` and validates without complaint. Run it with no
events at all:

```powershell
dc-twin run guide-strand.snapshot.json strand.scenario.json --output results/strand.json
```

```text
      0 ms  partial_service served=  600000 unserved=  400000 stranded=  400000
```

| Metric | Value |
|---|---:|
| Demanded energy | 600,000,000,000 mJ (166.666667 kWh) |
| Served energy | 360,000,000,000 mJ (100.000000 kWh) |
| Unserved energy | 240,000,000,000 mJ (66.666667 kWh) |
| Service ratio | 600,000 ppm (60%) |
| Peak stranded capacity | 400,000 W |
| Worst modeled state | `partial_service` |
| Alarms | 0 |

Check the stranded figure by hand:

```text
unserved_w                = 1,000,000 - 600,000 = 400,000 W
available source capacity = 1,200,000 + 1,200,000 = 2,400,000 W
used source capacity      = 600,000 W
unused                    = 1,800,000 W
stranded_capacity_w       = min(400,000, 1,800,000) = 400,000 W
```

1.8 MW of source capacity is sitting idle while 400 kW of demand goes unmet for
ten minutes, and the run raises no alarms whatsoever. This is the trap: a
topology that looks 2N on paper, declares itself `TWO_N` in its redundancy
group, and delivers 60% of its load from the first millisecond.

### Resolving it

Add one event — close the reserve cord at 120,000 ms:

```json
{ "id": "event-001-close-reserve-cord", "time_ms": 120000, "kind": "atomic_transfer",
  "open_connection_ids": [], "close_connection_ids": ["pdu-b-to-load-1"] }
```

```text
      0 ms  partial_service served=  600000 unserved=  400000 stranded=  400000
 120000 ms  single_path     served= 1000000 unserved=       0 stranded=       0
```

Unserved energy falls from 240,000,000,000 mJ to 48,000,000,000 mJ, and the
service ratio rises from 600,000 to 920,000 ppm. Note the state after the
close: `single_path`, not `two_n`, because path A still cannot carry the full
load alone through a 600 kW PDU. The redundancy evidence and the declared
`TWO_N` group disagree, permanently, and the engine never says so.

## The two causes, and telling them apart

Stranded capacity appears for two structurally different reasons.

### Cause one: the capacity cannot reach the load at all

The composite reference run, after UPS A dies at 390,000 ms:

```text
 390000 ms  no_path  served=       0 unserved= 1600000 stranded= 1600000
```

Utility B is available with 2 MW, and the loads are unreachable from it: PDU B
is in maintenance and the B cords were opened by an earlier transfer. So
`min(1,600,000 unserved, 2,000,000 unused) = 1,600,000 W`.

Same shape in the maintenance-overlap run from chapter 7:

```text
 168000 ms  no_path  served=       0 unserved= 1000000 stranded= 1000000
```

and in the shared-bus run from chapter 5, where a single failed component
strands both healthy paths at once.

The signature of this cause: stranded capacity equals unserved power exactly,
and the redundancy state is `no_path`.

### Cause two: a downstream rating throttles it

The trap topology above. Source capacity is plentiful and reaches the load, but
a component between them is too small. The signature: stranded capacity equals
unserved power, and the redundancy state is `partial_service` rather than
`no_path`.

To distinguish them, look at `connection_flow_w` for the affected segment. The
trap topology at `[0, 1000)`:

```text
flows   : {"pdu-a-to-load-1": 600000, "switchgear-a-to-pdu-a": 600000,
           "switchgear-b-to-pdu-b": 0, "utility-a-to-switchgear-a": 600000,
           "utility-b-to-switchgear-b": 0}
sources : {"utility-a": 600000, "utility-b": 0}
```

The A route carries flow, pinned at exactly 600,000 W — which is `pdu-a`'s
component rating, not the 1,000,000 W rating of the cord it feeds. The B route
carries nothing. Capacity is throttled.

Compare the maintenance-overlap run at `[168000, 169000)`:

```text
flows   : {"pdu-a-to-load-1": 0, "switchgear-a-to-ups-a": 0, "switchgear-b-to-ups-b": 0,
           "ups-a-to-pdu-a": 0, "utility-b-to-switchgear-b": 0}
sources : {"utility-b": 0}
```

Every flow is zero and an eligible source is listed at 0 W. Capacity is
isolated.

The rule: if some route is carrying flow at exactly the rating of a component
or connection on it, capacity is throttled. If every route reads zero while a
source is still listed, capacity is isolated. Note that the saturated element
is often a *component* rating rather than the connection rating, so check both
against the snapshot.

## When stranded capacity is zero and you still have a problem

Two cases, both important.

**Everything available is already committed.** Chapter 4's priority run: 600 kW
of source, 900 kW of demand, 300 kW unserved, and stranded capacity **zero**,
because the single source is fully loaded. Nothing is isolated. There is simply
not enough.

```text
      0 ms partial_service  unserved= 300000 stranded=      0
```

**Everything that could help is dead.** The single-feed run in chapter 5, after
the UPS empties:

```text
 168000 ms  no_path  served= 0  unserved= 1000000  stranded=       0
```

The failed utility contributes no available source capacity and the depleted
UPS has no energy, so unused available capacity is zero. The bundled N
reference scenario behaves identically, and its documentation states the point
directly: nothing is isolated from the load; there is simply nothing left to
serve it.

So `stranded_capacity_w == 0` means one of three things — everything is served,
everything available is committed, or nothing is available — and you cannot
tell which from the figure alone. Always read it alongside `unserved_w`.

## What stranded capacity is not

**It is not spare capacity or design margin.** The metric is defined as zero
whenever demand is fully served. A healthy 2N topology with 100% headroom
reports `stranded_capacity_w: 0` in every segment, and so does a topology with
no headroom at all. If you want to know your margin, dc-twin does not report
it; you compute it from the ratings yourself.

**It is not firm capacity, reserve, or N-1 capability.** Those are design
quantities. This is a runtime observation about one interval.

**It is not a switching recommendation.** The model specification is explicit:
it is not a claim that a switch can safely be closed. Stranded capacity of
1.6 MW says "1.6 MW of eligible source is idle while 1.6 MW goes unserved". It
does not say the connection between them is closable, that closing it is safe,
that it would not parallel sources, or that any device exists to close it.

Every one of the isolation examples above has a *modelled* route that would fix
it, because the model only knows about connections you drew. Whether that route
is a real breaker, a temporary cable, or a line on a drawing that was never
built is not something the model can distinguish.

## Using it well

Stranded capacity is at its best as a **design review signal**, run against a
healthy scenario with no events:

1. Run the topology with an empty `events` array.
2. If `peak_stranded_capacity_w` is nonzero, you have capacity that cannot
   reach load in the *normal* configuration. That is almost always worth
   investigating, and it is exactly what the trap topology above exposes.
3. Then run the failure scenarios, and read stranded capacity at each
   transition as "what was available and could not help".

The metric will not find every problem — chapter 5's shared-bus run reports
zero stranded capacity until the moment the bus fails — but a nonzero value on
a healthy run is a strong signal and costs one command to check.

---

Previous: [13. Unserved energy](13-unserved-energy.md) ·
Next: [15. Result hashes, determinism and replay](15-determinism-and-replay.md)
