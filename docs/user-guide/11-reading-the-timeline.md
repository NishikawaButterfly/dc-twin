# 11. Reading the timeline

The timeline is the primary output. Metrics are integrals over it, alarms are
annotations on it, and the hash is a fingerprint of it. If you can read a
segment correctly you can read everything else.

## What a segment is

A segment is a half-open interval `[start_ms, end_ms)` during which every
modelled quantity is constant. Here is a real one, the first segment of the
composite reference run:

```json
{
 "start_ms": 0,
 "end_ms": 1000,
 "demand_w": 1600000,
 "served_w": 1600000,
 "unserved_w": 0,
 "stranded_capacity_w": 0,
 "redundancy_state": "two_n",
 "load_service_w": { "it-load-1": 800000, "it-load-2": 800000 },
 "source_power_w": { "utility-a": 800000, "utility-b": 800000 },
 "connection_flow_w": {
  "ats-a-to-transformer-a": 800000, "ats-b-to-transformer-b": 800000,
  "pdu-a-to-load-1-normal": 400000, "pdu-a-to-load-2-normal": 400000,
  "pdu-b-to-load-1-normal": 400000, "pdu-b-to-load-2-normal": 400000,
  "switchgear-a-to-ups-a": 800000, "switchgear-b-to-ups-b": 800000,
  "transformer-a-to-switchgear-a": 800000, "transformer-b-to-switchgear-b": 800000,
  "ups-a-to-pdu-a": 800000, "ups-b-to-pdu-b": 800000,
  "utility-a-to-ats-a": 800000, "utility-b-to-ats-b": 800000
 },
 "battery_energy_mj": { "ups-a": 432000000000, "ups-b": 432000000000 },
 "causal_event_ids": ["system.initialized"],
 "state_hash": "362778558f48e21606829577e060f126e1568b80eb4c0b718db4d2f9502f2f40"
}
```

## Where segment boundaries come from

Four sources, and only four:

1. **Scheduled event times** from the scenario.
2. **Requested resolution boundaries**, at every multiple of `resolution_ms`.
3. **Derived UPS milestones** — low-energy threshold and depletion — computed
   at the exact integer millisecond.
4. **The horizon.**

Boundaries 1, 3 and 4 are what the simulation needs to be correct. Boundary 2
is what *you* asked for. This is why changing `resolution_ms` changes the
segment count without changing a single metric, as chapter 9 demonstrated.

## The rule that catches everyone

> Power and flow values apply **throughout** the interval.
> `battery_energy_mj` and `state_hash` represent the state **at `end_ms`**,
> after this interval's energy debit and before any transition at that same
> boundary.

Here is what that looks like in practice. The last segment before UPS A dies in
the composite run:

```json
{
 "start_ms": 389000, "end_ms": 390000,
 "battery_energy_mj": { "ups-a": 0, "ups-b": 432000000000 },
 "source_power_w": { "ups-a": 1600000, "utility-b": 0 },
 "redundancy_state": "battery_backed",
 "served_w": 1600000, "unserved_w": 0, "stranded_capacity_w": 0,
 "causal_event_ids": ["system.ups_low_energy.ups-a.336000"]
}
```

UPS A is shown at **zero** stored energy while simultaneously supplying
**1,600,000 W** and the load is **fully served**. Nothing is contradictory: for
the whole of `[389000, 390000)` the battery was supplying 1.6 MW, and at
390,000 ms — the instant the interval closes — it reached zero.

Read `battery_energy_mj` as "how much is left when this interval ends", never
as "how much was available during it". If you plot the battery series against
the power series without shifting one of them, your chart will show the battery
empty for a second while still delivering full load, and you will spend an
afternoon looking for a bug that is not there.

The very next segment shows the consequence:

```json
{
 "start_ms": 390000, "end_ms": 391000,
 "battery_energy_mj": { "ups-a": 0, "ups-b": 432000000000 },
 "source_power_w": { "utility-b": 0 },
 "load_service_w": { "it-load-1": 0, "it-load-2": 0 },
 "redundancy_state": "no_path",
 "served_w": 0, "unserved_w": 1600000, "stranded_capacity_w": 1600000,
 "causal_event_ids": ["system.ups_depleted.ups-a.390000"]
}
```

## Reading each field

### `demand_w`, `served_w`, `unserved_w`

Total across all loads. The invariant `unserved_w = demand_w - served_w` holds
in every segment and is asserted internally; if it ever failed the engine would
raise `engine.power_balance` rather than emit the segment.

### `load_service_w`

Per-load allocation for this interval. This is where the sequential priority
policy from chapter 4 becomes visible — a starved load shows `0` while its
peers show their full demand.

### `source_power_w`

How much each eligible source actually delivered. **Sources appear here with a
value of zero.** In the segment above, `utility-b` is listed at 0 W: it was
available and eligible, and delivered nothing because it could not reach the
load. A source's presence in this map means "eligible", not "supplying".

This map is also where you see which UPS units are acting as batteries — but
read the value, not the key. A `ups-*` key with a positive value is a unit
discharging. A `ups-*` key at `0 W` is a unit that was islanded from its own
upstream feed, was therefore eligible to discharge, and was not called on
because a live source could reach the load. Stored energy is the last source
class the allocation reaches for, so that second case is the common one on a
redundant topology.

### `connection_flow_w`

Per-connection flow for this interval, and the field most likely to be
over-read.

**These are feasible flows from a max-flow solution, not predicted currents.**
The solver finds *an* allocation that satisfies every rating; it does not find
*the* allocation that a real network would produce. Recall from chapter 3 what
this looks like on a symmetric dual-cord load with 1 MW cords:

```text
   source_power_w : {"utility-a": 1000000, "utility-b": 0}
   flows>0        : {"pdu-a-to-load-1": 1000000, ...}
```

Both cords closed, both paths healthy, and the model put 100% of the load on
cord A. In reality the split would be near 50/50. The model is not wrong — that
allocation is feasible and demonstrates the capacity exists — but the number
against `pdu-a-to-load-1` is not a prediction of what that cord would carry.

Use connection flows to answer "did capacity reach the load, and through
what". Do not use them for cable sizing, loading studies, metering
reconciliation, or anything else that depends on the split being real.

The bundled `reference-2n` snapshot gets a plausible-looking 400/400 split not
because the solver balanced anything, but because the cord ratings are 400 kW
each and an 800 kW load has nowhere else to go.

**Presence in the map is itself information.** A connection appears if and only
if it was closed *and* both its endpoints were available for that interval.
Compare the composite run's first segment with the segment after UPS A dies:

| Segment | Absent connections |
|---|---|
| `[0, 1000)` | the two generator ties and all four transfer cords — all open |
| `[390000, 391000)` | the two generator ties (open), the four `pdu-b` cords (opened at 62,000 ms), `ups-b-to-pdu-b` (`pdu-b` is in maintenance), `utility-a-to-ats-a` (`utility-a` has failed) |

In that second segment, twelve connections are present with a flow of `0`.
Those are edges that existed and carried nothing. So: a key at zero means
"available and idle"; a missing key means "open, or an endpoint is out". The
two are different conditions and the map distinguishes them.

### `redundancy_state`

Per-segment evidence, defined in chapter 5. Independent of the actual
allocation.

### `stranded_capacity_w`

Nonzero only while demand is unserved. Chapter 14.

### `causal_event_ids`

The event or events that produced this state. Internal transitions have
synthetic IDs of the form `system.<kind>.<component>.<time>`:

```text
system.initialized
system.ups_low_energy.ups-a.336000
system.ups_depleted.ups-a.390000
```

The ID is self-describing, which makes it worth propagating into whatever you
build on top. A segment tagged `system.ups_depleted.ups-a.390000` tells the
whole story without a lookup.

### `state_hash`

SHA-256 of the canonical runtime state at `end_ms`: component statuses,
connection positions, running generators, demands, battery energies, and which
alarms have latched. Segments with identical state share a hash, so a long run
of identical hashes is a stable period and a change is a real state change.

Note what the state hash does *not* cover: component kind, ratings, labels, or
anything from the snapshot that cannot change during a run. Chapter 2's kind-
swap experiment produced an identical sequence of state hashes precisely
because none of those are in it.

## The transition ledger

Alongside the timeline, `transitions` records every state change with
before/after hashes and the alarms raised and cleared:

```json
{"sequence": 6, "time_ms": 390000, "event_id": "system.ups_depleted.ups-a.390000", "event_kind": "ups_depleted", "target_id": "ups-a", "alarms_raised": ["alarm-0005-ups-energy-depleted", "alarm-0006-load-unserved"], "alarms_cleared": []}
```

```json
{"sequence": 8, "time_ms": 422000, "event_id": "event-006-transfer-loads-to-b", "event_kind": "atomic_transfer", "target_id": null, "alarms_raised": [], "alarms_cleared": ["alarm-0006-load-unserved"]}
```

The composite run has nine transitions against 600 segments. Read the
transitions first to find *when* things happened, then go to the segments for
*what the state was*. The transition list is the shortest useful summary of any
run.

The first entry is always `sequence: 0`, `event_id: "system.initialized"` at
`time_ms: 0`, recording the initial state before any event.

## A practical reading procedure

For any run:

1. Read `metrics.modeled_redundancy_state` and `metrics.unserved_energy_mj`.
   Those two tell you whether anything went wrong at all.
2. Read the `transitions` list end to end. Nine lines usually.
3. Collapse the timeline to the segments where state changed. Six hundred
   segments become five lines. Every state-run listing in this guide was
   produced with this script:

```python
"""Collapse a dc-twin timeline to the segments where the state changed."""

import json
import sys

result = json.load(open(sys.argv[1], encoding="utf-8"))
previous = None
for segment in result["timeline"]:
    key = (
        segment["redundancy_state"],
        segment["served_w"],
        segment["unserved_w"],
        segment["stranded_capacity_w"],
    )
    if key != previous:
        print(
            f"{segment['start_ms']:>8} ms  {segment['redundancy_state']:<16}"
            f" served={segment['served_w']:>8}"
            f" unserved={segment['unserved_w']:>8}"
            f" stranded={segment['stranded_capacity_w']:>8}"
        )
        previous = key
```

```powershell
python collapse.py results/maint.json
```

```text
       0 ms  two_n            served= 1000000 unserved=       0 stranded=       0
   30000 ms  single_path      served= 1000000 unserved=       0 stranded=       0
   60000 ms  battery_backed   served= 1000000 unserved=       0 stranded=       0
  168000 ms  no_path          served=       0 unserved= 1000000 stranded= 1000000
  240000 ms  single_path      served= 1000000 unserved=       0 stranded=       0
```

4. Only then open individual segments, for the boundaries that matter.

---

Previous: [10. Running a scenario](10-running-a-scenario.md) ·
Next: [12. Reading alarms](12-reading-alarms.md)
