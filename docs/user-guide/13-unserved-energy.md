# 13. Unserved energy

Unserved energy is the headline number of any dc-twin run and the one most
likely to be quoted out of context. This chapter states exactly what it counts.

## The definition

```text
unserved_energy_mj = Σ over segments (unserved_w × segment_duration_ms)
```

where, per segment, `unserved_w = demand_w - served_w`. The arithmetic is exact
integer, so the figure has no rounding error at all.

The engine's own explanation block says the same thing:

```json
{
 "formula": "sum(unserved_w * segment_duration_ms)",
 "input_refs": ["snapshot:reference-2n", "scenario:REF-DC-2N-001"],
 "summary": "Integrated 51200000000 mJ of unmet modeled demand."
}
```

## What it counts

**Watts of demand that the graph could not deliver, multiplied by the
milliseconds they went undelivered.** Nothing else.

It counts a shortfall identically whether the cause is a failed source, an open
connection, a component in maintenance, an undersized rating, or a load that
was never reachable in the first place. It counts partial shortfalls
(400 kW unmet out of 1 MW) exactly the same way it counts total ones.

Worked on the composite reference run, where the loss is a clean block:

```text
interruption from 390,000 ms to 422,000 ms
duration           = 32,000 ms
unserved_energy_mj = 1,600,000 W × 32,000 ms
                   = 51,200,000,000 mJ
                   = 14.222222 kWh
```

And the engine reports `"unserved_energy_mj": 51200000000`. Exactly.

## What it does not count

### It does not count the consequences

51.2 GJ of unmet demand is a number about watts and milliseconds. It says
nothing about how many racks lost power, whether they had internal ride-through,
whether the shutdown was orderly, how long recovery took, what data was lost,
what it cost, or whether anyone noticed. The model ends at the load's terminal
node.

### It does not count anything outside the horizon

The single-feed run in chapter 5 reports 432,000,000,000 mJ unserved. That is
not "the outage was 120 kWh"; the outage had not ended when the scenario
stopped. The utility was never restored and the horizon simply expired at
600,000 ms. Double the horizon and the figure doubles, with nothing about the
design having changed.

Any unserved-energy figure is therefore a statement about a window you chose.
Always quote the horizon alongside it.

### It does not count demand you did not declare

Demand is exactly what your `demand_w` fields and `load_step` events say. If
the real load is 20% higher than the figure you authored, the unserved energy
is understated and there is no indication anywhere in the result.

Worse, the relationship is not proportional. A path with 200 kW of headroom
absorbs a 10% demand error invisibly and then fails completely at 20%. Ratings
and demand are the two inputs where a small authoring error produces a
qualitatively different answer, not a slightly different one.

### It does not distinguish which load was lost

`unserved_energy_mj` is a total. A run that starved one 300 kW lab load for two
minutes and a run that dropped a 300 kW critical load for two minutes produce
the identical figure. Per-load detail exists only in
`timeline[].load_service_w`, segment by segment, and no aggregate metric
carries it.

If which load matters to your analysis — and it usually does — you must
reconstruct it yourself from the timeline. Chapter 16 covers the tooling gap.

## The related metrics, and their traps

### `interruption_duration_ms`

The total duration of segments with **any** unserved demand. Not the duration
of a total loss. In chapter 4's priority run, `interruption_duration_ms` is
120,000 ms while the two higher-priority loads ran without interruption for the
entire horizon — the figure is counting a period in which one lower-priority
load was starved.

### `interruption_count`

Increments on each transition from full service to any under-service. Two
traps:

- A run that *begins* under-served counts as 1, with nothing interrupted.
  Chapter 14's stranded run reports `"interruption_count": 1` and
  `"interruption_duration_ms": 600000` — the entire horizon — for a condition
  that was true before the clock started.
- The count says nothing about depth. One transition from 1.6 MW served to
  1.599 MW served counts the same as one transition to zero.

### `service_ratio_ppm`

```text
service_ratio_ppm = (served_energy_mj × 1,000,000 + demanded_energy_mj // 2)
                    // demanded_energy_mj
```

Deterministic integer round-half-up. When demanded energy is zero the ratio is
defined as 1,000,000 ppm.

The ratio is served energy over demanded energy **for this scenario**. Because
demand is the denominator, anything that reduces demand improves the ratio. The
zero-demand run in chapter 4 demonstrates it: stepping every load to zero
partway through raises the reported ratio, because the shortfall from the first
two minutes is divided by a smaller total.

The ratio is comparable between two runs only if they share a horizon and a
demand profile. It is never an availability figure, an SLA, an uptime
percentage, or anything with an annual denominator. The web explorer labels the
tile "Not a site-availability or SLA claim" for precisely this reason.

### `peak_served_w` and `minimum_served_w`

Extrema of served power across segments, with zero-demand segments excluded
from the minimum. Both follow demand, not health. Chapter 4 shows
`minimum_served_w` falling because loads were switched off.

## How to quote the figure

A defensible sentence looks like this:

> In scenario `GUIDE-2N-MAINT-OVERLAP` on snapshot `guide-2n`
> (`snapshot_hash c6c6f0…`), over a 600,000 ms horizon, the model reports
> 72,000,000,000 mJ (20.0 kWh) of unserved demand, arising from a single
> 72,000 ms period beginning at 168,000 ms when UPS A depleted while PDU B was
> in its maintenance window.

Every element earns its place: the scenario, the snapshot, the horizon, the
exact integer, the human conversion, and the mechanism. Drop any of them and
the sentence starts being able to mean something it should not.

An indefensible sentence, from the same run:

> The design loses 20 kWh in a utility failure.

It does not. It lost 20 kWh in *this* utility failure, at *this* moment, with
*this* maintenance window open. Chapter 5 runs the same utility failure on the
same topology with no maintenance window and loses nothing at all.

---

Previous: [12. Reading alarms](12-reading-alarms.md) ·
Next: [14. Stranded capacity](14-stranded-capacity.md)
