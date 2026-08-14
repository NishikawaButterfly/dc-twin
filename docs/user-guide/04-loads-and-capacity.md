# 4. Loads and capacity

Capacity is the only physics in this model, so the allocation policy is the
single most important behaviour to understand. This chapter states the policy,
runs a deliberate shortage, and shows what the numbers do and do not tell you.

## The allocation policy

For each interval the engine builds the *available network*: components whose
state is `available`, connections that are closed and whose endpoints are both
available, and eligible sources attached to a conceptual super-source.

It then considers loads one at a time, in ascending
`(priority, service_order, component_id)` order. For each load it runs an
integral maximum-flow calculation and allocates as much of that load's current
demand as the remaining network capacity permits. Capacity consumed by an
earlier load is deducted before the next load is considered.

Three properties follow, and all three matter:

1. **It is sequential, not simultaneous.** The first load takes what it needs
   before the second is considered at all.
2. **It is not proportional.** There is no fair-share, no load shedding
   percentage, and no partial derating across loads. A lower-priority load is
   starved completely before a higher-priority load gives up a single watt.
3. **It is not an optimisation.** This is not economic dispatch, not optimal
   power flow, and not a prediction of how protective devices would behave. It
   is a deterministic, auditable rule chosen because it can be checked by hand.

Determinism is enforced by sorting: source identifiers and adjacency lists are
sorted before traversal, so an otherwise-equivalent graph does not depend on
dictionary order, file-system order or database order.

## A deliberate shortage

Consider a single 600 kW feed supplying three 300 kW loads through a 600 kW
PDU. Total demand is 900 kW against 600 kW of capacity. The loads differ only
in priority:

| Load | Demand | Priority | Service order |
|---|---:|---:|---:|
| `it-load-critical` | 300,000 W | 1 | 1 |
| `it-load-normal` | 300,000 W | 2 | 1 |
| `it-load-lab` | 300,000 W | 3 | 1 |

Two `load_step` events reduce demand later: the lab load drops to zero at
120,000 ms, and the normal load drops to 150,000 W at 240,000 ms.

```powershell
dc-twin run guide-priority.snapshot.json priority.scenario.json --output results/priority.json
```

The timeline, collapsed to the segments where something changed:

```text
      0 ms partial_service  unserved= 300000 stranded=      0 loads={"it-load-critical": 300000, "it-load-lab": 0, "it-load-normal": 300000}
 120000 ms single_path      unserved=      0 stranded=      0 loads={"it-load-critical": 300000, "it-load-lab": 0, "it-load-normal": 300000}
 240000 ms single_path      unserved=      0 stranded=      0 loads={"it-load-critical": 300000, "it-load-lab": 0, "it-load-normal": 150000}
```

The policy is visible in the first line. Two loads are served in full and the
third gets nothing at all. Nobody is served 200 kW of their 300 kW. The
priority-3 load absorbs the entire 300 kW shortfall.

And the metrics:

```json
{
 "demanded_energy_mj": 342000000000,
 "interruption_count": 1,
 "interruption_duration_ms": 120000,
 "minimum_served_w": 450000,
 "modeled_redundancy_state": "partial_service",
 "peak_demand_w": 900000,
 "peak_served_w": 600000,
 "peak_stranded_capacity_w": 0,
 "served_energy_mj": 306000000000,
 "service_ratio_ppm": 894737,
 "unserved_energy_mj": 36000000000
}
```

Check it by hand. Demand is 900 kW for 120 s, then 600 kW for 120 s, then
450 kW for 360 s:

```text
demanded_energy_mj = 900,000 * 120,000 + 600,000 * 120,000 + 450,000 * 360,000
                   = 108,000,000,000 + 72,000,000,000 + 162,000,000,000
                   = 342,000,000,000 mJ
served_energy_mj   = 600,000 * 120,000 + 600,000 * 120,000 + 450,000 * 360,000
                   = 306,000,000,000 mJ
unserved_energy_mj = 300,000 W * 120,000 ms = 36,000,000,000 mJ
service_ratio_ppm  = round_half_up(306e9 * 1,000,000 / 342e9) = 894,737 ppm
```

Exact, to the last digit.

## Three traps in that output

This run is small enough to reason about completely, which makes it a good
place to see three metrics behave in ways their names do not suggest.

### `interruption_count: 1` describes nothing that was interrupted

The lab load was never served, from `0 ms` onward. Nothing was interrupted; a
load was simply never picked up. The engine counts an "interruption" as any
transition from *fully served* to *any* under-service, and a run that begins
under-served counts as entering that state once. The critical and normal loads
ran without a single second of shortfall for the entire horizon.

If you quote "one interruption of two minutes" from this run, every word is
defensible against the metric definition and the sentence is still misleading.

### `minimum_served_w: 450000` went down because demand went down

Served power falls to 450 kW at the end of the run, and that is the minimum
recorded. But service *improved* over the run: at the start 300 kW was unmet,
at the end nothing was. `minimum_served_w` and `peak_served_w` track how much
power flowed, which follows demand, not health. A run where every load is
switched off scores a very low minimum served and a perfect service ratio.

One refinement worth knowing: segments with zero demand are excluded from
`minimum_served_w`. In a run where all loads step to zero, the reported minimum
is the lowest served power *among segments that demanded something*, which can
sit above zero while the tail of the run serves nothing at all because nothing
was asked for.

### `peak_stranded_capacity_w: 0` while 300 kW went unserved

There was a shortfall for two minutes and stranded capacity stayed at zero,
because the single 600 kW source was fully committed. Stranded capacity is not
"how short you were". Chapter 14 covers it properly.

## Setting demand: `load_step`

Demand changes only through `load_step` events, and the new value may not
exceed the load component's own `capacity_w`:

```json
{"detail": "Event event-002-step sets demand above it-load-1's rating.", "error_code": "scenario.load_above_rating"}
```

So a load's `capacity_w` acts as its maximum authorised demand. Demand may be
stepped to `0`; when *every* load is at zero the segment's redundancy state
becomes `no_demand` and service-path evidence is not evaluated:

```text
      0 ms partial_service  demand= 900000 served= 600000 unserved= 300000
 120000 ms no_demand        demand=      0 served=      0 unserved=      0
```

Note what that does to the aggregate: the run above reports
`service_ratio_ppm: 666667` because the shortfall in the first two minutes is
divided by a much smaller total demand once the loads switch off. Shrinking
demand improves the service ratio. That is arithmetically correct and
analytically useless, and it is one more reason chapter 19 insists the ratio is
only comparable between runs over the same demand profile.

## Priority in practice

`priority` runs 1 to 100 and `service_order` runs 1 to 10,000; ties break on
`component_id` as a string. Use them deliberately:

- Give genuinely different criticality tiers different `priority` values.
- Use `service_order` to make the order *within* a tier explicit rather than
  letting it fall back to alphabetical component IDs. The bundled `reference-2n`
  snapshot does this: `it-load-1` and `it-load-2` share `priority: 1` and are
  separated by `service_order: 1` and `2`.
- Do not read priority as a statement about the facility. It is a sort key that
  determines who is starved first in a modelled shortage. It has no
  relationship to life-safety classification, to what a real system would shed,
  or to anything a control system would do.

## The one thing capacity never does

Nothing in this model ever exceeds a rating, even briefly. There is no
short-time overload, no thermal inertia, no `I²t`, and no distinction between a
momentary and a sustained condition. A path that is 1 W short delivers 1 W less
for the whole interval. Whether a real system would ride through that, trip on
it, or not notice it is outside the model entirely.

---

Previous: [3. Building a topology](03-building-a-topology.md) ·
Next: [5. Redundancy in this model's terms](05-redundancy.md)
