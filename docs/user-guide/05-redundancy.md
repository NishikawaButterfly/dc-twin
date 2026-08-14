# 5. Redundancy in this model's terms

The engine reports a redundancy state for every timeline segment and a worst
observed state for the run. The state names look like industry terms. They are
not industry terms. This chapter defines what each one actually asserts, shows
the same failure landing differently on N and 2N, and demonstrates two ways the
reported state can mislead you.

## The seven states

For each segment the engine reports exactly one of:

| State | Assertion |
|---|---|
| `two_n` | At least two distinct non-battery source paths could each serve the total demand alone |
| `single_path` | Exactly one non-battery source path could serve the total demand alone |
| `supported` | Non-battery capacity fully serves demand, but the graph proves neither `two_n` nor `single_path` |
| `battery_backed` | Battery supply is required to serve total demand; no non-battery path could do it alone |
| `partial_service` | Served power is greater than zero and less than demand |
| `no_path` | Served power is zero |
| `no_demand` | Current demand is zero, so path evidence does not apply |

The run-level `modeled_redundancy_state` is the **worst** non-zero-duration
state observed, ordered worst to strongest: `no_path`, `partial_service`,
`battery_backed`, `single_path`, `supported`, `two_n`. `no_demand` is ignored
unless every segment has zero demand.

That "worst observed" rule means a run-level state of `no_path` can describe a
single second in a ten-minute run that was otherwise perfect. The run-level
figure is a floor, not a summary.

## How the evidence is calculated

This is the part that surprises people, so it is worth stating precisely.

For each eligible non-battery source, the engine runs a **separate, hypothetical
full-demand allocation** asking: could this source alone serve every watt of
current demand? That hypothetical preserves the current state of everything
upstream — component availability, connection positions, component ratings,
connection ratings — with one exception. It hypothetically closes the eligible
load-input connections belonging to that source's own available path.

Three things follow:

- **The evidence is independent of what actually happened.** The reported state
  does not describe where the power came from in that segment. It describes
  what a path *could* have done in a separate calculation.
- **The hypothetical closure is not a switching recommendation.** The engine
  closes those load edges only inside its own arithmetic. It is not asserting
  the transfer is available, automatic, safe, or that any device would perform
  it.
- **Only paths `A` and `B` can qualify.** The calculation checks whether the
  qualifying source's `path` tag is `A` or `B`. Nothing else counts.

## N and 2N, the same failure

The two snapshots from chapter 3 differ only by the second path. Inject exactly
the same event into both: `utility-a` fails at 60,000 ms and is never restored.
Horizon 600,000 ms, resolution 1,000 ms.

```json
{
  "id": "event-001-utility-a-failure",
  "time_ms": 60000,
  "kind": "component_failure",
  "component_id": "utility-a",
  "status": "failed"
}
```

### On the single feed

```powershell
dc-twin run guide-n.snapshot.json feed-loss-n.scenario.json --output results/n.json
```

```text
      0 ms  single_path     served= 1000000 unserved=       0 stranded=       0 battery=-
  60000 ms  battery_backed  served= 1000000 unserved=       0 stranded=       0 battery=ups-a
 168000 ms  no_path         served=       0 unserved= 1000000 stranded=       0 battery=-
```

| Metric | Value |
|---|---:|
| Demanded energy | 600,000,000,000 mJ (166.666667 kWh) |
| Served energy | 168,000,000,000 mJ (46.666667 kWh) |
| Unserved energy | 432,000,000,000 mJ (120.000000 kWh) |
| Service ratio | 280,000 ppm (28%) |
| Interruption duration | 432,000 ms |
| Interruption count | 1 |
| Worst modeled state | `no_path` |

The UPS carries the load for 108 seconds and then the room is dark for the
remaining 432 seconds.

### On the redundant pair

```powershell
dc-twin run guide-2n.snapshot.json feed-loss-2n.scenario.json --output results/2n.json
```

```text
      0 ms  two_n           served= 1000000 unserved=       0 stranded=       0 battery=-
  60000 ms  single_path     served= 1000000 unserved=       0 stranded=       0 battery=ups-a
```

| Metric | Value |
|---|---:|
| Demanded energy | 600,000,000,000 mJ (166.666667 kWh) |
| Served energy | 600,000,000,000 mJ (166.666667 kWh) |
| Unserved energy | 0 mJ |
| Service ratio | 1,000,000 ppm (100%) |
| Interruption duration | 0 ms |
| Interruption count | 0 |
| Worst modeled state | `single_path` |

Same event, same demand, same horizon. One design loses 120 kWh and the other
loses nothing. That is the redundancy, stated in the only terms this model has.

Read the `battery=ups-a` marker on the second line carefully: that column lists
the UPS units present in `source_power_w`, and presence means *eligible*. From
60,000 ms UPS A is islanded from its own feed and eligible to discharge, and it
delivers 0 W throughout, because utility B can reach the load. The redundant
pair finishes the run with both batteries at their full
108,000,000,000 mJ.

The CLI will state the difference for you:

```powershell
dc-twin compare results/n.json results/2n.json
```

```json
{"left_run_id": "run-97219503d3fb95ea", "metric_differences": {"interruption_count": {"left": 1, "right": 0}, "interruption_duration_ms": {"left": 432000, "right": 0}, "minimum_served_w": {"left": 0, "right": 1000000}, "modeled_redundancy_state": {"left": "no_path", "right": "single_path"}, "served_energy_mj": {"left": 168000000000, "right": 600000000000}, "service_ratio_ppm": {"left": 280000, "right": 1000000}, "unserved_energy_mj": {"left": 432000000000, "right": 0}}, "right_run_id": "run-72e2cb542c7489b9", "same_computation": false}
```

## Two ways the state misleads

### The reported state is not where the power came from

Look again at the 2N run after 60,000 ms. The state is `single_path`, which
asserts that one non-battery path could carry the full demand alone. True:
utility B could. But the state says nothing about which source actually did,
and that is a separate reading:

```text
--- segment 100000-101000  state=single_path
   source_power_w : {"ups-a": 0, "utility-b": 1000000}
   flows>0        : {"pdu-b-to-load-1": 1000000, "switchgear-b-to-ups-b": 1000000,
                     "ups-b-to-pdu-b": 1000000, "utility-b-to-switchgear-b": 1000000}
   battery@end    : {"ups-a": 108000000000, "ups-b": 108000000000}
```

Utility B carries the whole load and UPS A, which is islanded and eligible,
delivers nothing. Note that UPS A still appears in the map at `0 W`: presence
means eligible, not supplying.

That is the allocation policy doing what it should. Sources belong to two
classes, and stored energy is a last resort. Each interval is solved in two
stages: first every load from the live sources alone — available utilities and
running generators, with no battery edge in the network at all — and then, only
for whatever is still short, the same loads again with the battery edges added.
A battery therefore supplies exactly the demand that no live source can reach.

The `single_path` state and the `source_power_w` map still answer different
questions, and you need both. `single_path` does not mean "running on one
utility"; it means "one path could carry this". Which source is carrying it is
in the map, and how long a battery could keep carrying it is in
`battery_energy_mj`. Chapter 18 works through reading the three together.

### The reported state depends on a metadata string

Take the `guide-2n` snapshot and change nothing except the `path` tag on every
component, from `A`/`B`/`shared` to `shared` throughout. Same ratings, same
connections, same closed positions, same load.

```text
  worst state: supported
  segment 0 state: supported | sources: {"utility-a": 1000000, "utility-b": 0}
```

The identical topology now reports `supported` instead of `two_n`, forever. No
qualifying path exists, because `_source_path_can_serve_total` only counts
sources whose `path` is `A` or `B`.

This is a real trap. If you organise a topology by function, by room, by
building or by voltage level rather than by A/B path, dc-twin will report the
weaker state permanently and you will have no indication why. `path` is not a
label for your convenience; it is an input to the redundancy calculation.

## What N, N+1 and 2N mean here

Against that background:

**2N** means the model found two distinct source paths, tagged `A` and `B`,
each of which could serve the total current demand alone in the current graph
state. It is a statement about one instant and one demand figure. It says
nothing about whether the two paths are genuinely independent, because the
model has no concept of independence beyond graph reachability.

That is worth demonstrating, because it is the single most quotable thing the
state name gets wrong. Take `guide-2n`, remove the two direct cords, and route
both PDUs into one shared 1.2 MW final bus that feeds the load. Every other
rating and position is unchanged. Fail that shared bus at 120,000 ms:

```text
      0 ms  two_n           served= 1000000 unserved=       0 stranded=       0
 120000 ms  no_path         served=       0 unserved= 1000000 stranded= 1000000
```

```text
 120000 ms  critical component_failed  bus-shared entered the modeled failed state.
 120000 ms  critical load_unserved     Modeled unserved load increased to 1000000 W.
```

The model reported `two_n` right up to the instant a single component took the
entire load out. Both utilities remained available and both UPS units finished
the run with their full 108,000,000,000 mJ, because neither had lost its own
upstream feed. `two_n` in this model means "two source paths could each carry
this", and nothing whatsoever about single points of failure downstream of
where those paths converge.

**N+1** has no state name at all. There is no `n_plus_1` value. A reserve unit
that absorbs a failure shows up as whatever the graph then supports — in the
bundled `reference-n-plus-1` run, the reserve pickup reports `battery_backed`
during the bridge and `single_path` either side of it. The redundancy is
demonstrated by the *absence* of unserved energy across a component failure,
not by a state name.

**N** likewise has no state name. A single-path design in normal operation
reports `single_path`, which is the same value a 2N design reports after losing
one path. The two are indistinguishable from the state alone.

Which brings us to the `redundancy_groups` block. You may declare
`{"mode": "TWO_N", "members": ["utility-a", "utility-b"]}` in a snapshot and
the engine will record it, hash it, and ignore it. The stranded-capacity
topology in chapter 14 declares exactly that group and reports `single_path` at
best, because PDU A is undersized and only path B can carry the load alone. The
declaration and the evidence disagree, and the engine never mentions it.

Declared redundancy is design intent. Reported redundancy is graph evidence for
one instant. Treat any disagreement between them as a question to investigate,
never as something the tool has reconciled for you.

---

Previous: [4. Loads and capacity](04-loads-and-capacity.md) ·
Next: [6. UPS batteries and runtime](06-ups-and-runtime.md)
