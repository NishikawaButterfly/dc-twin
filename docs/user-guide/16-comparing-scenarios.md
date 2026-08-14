# 16. Comparing two scenarios

Comparison is where most real analysis happens: this design against that one,
this maintenance window against a different one, this battery size against a
larger one. dc-twin supports it partially. This chapter states plainly what it
does, what it does not, and what you have to do by hand.

## What exists

Three routes, none of them complete.

| Route | Compares | Works on |
|---|---|---|
| `dc-twin compare` | metrics and the computation hash | any two result files |
| Web explorer *Compare runs* | five metrics plus a milestone table | the five bundled fixtures only |
| The API | nothing — there is no comparison route | — |

## The CLI: `dc-twin compare`

```powershell
dc-twin compare results/n.json results/2n.json
```

```json
{"left_run_id": "run-97219503d3fb95ea", "right_run_id": "run-0ca87f32ca8385a8", "same_computation": false, "metric_differences": {"interruption_count": {"left": 1, "right": 0}, "interruption_duration_ms": {"left": 432000, "right": 0}, "minimum_served_w": {"left": 0, "right": 1000000}, "modeled_redundancy_state": {"left": "no_path", "right": "single_path"}, "served_energy_mj": {"left": 168000000000, "right": 600000000000}, "service_ratio_ppm": {"left": 280000, "right": 1000000}, "unserved_energy_mj": {"left": 432000000000, "right": 0}}}
```

It reports two things: whether the computation hashes match, and every metric
key whose value differs, with both values. Keys that agree are omitted.

It operates on **result files**, not on scenarios, so both runs must already
exist. It does not care whether they came from the same snapshot, the same
horizon, or the same demand profile. It will happily compare a run on `guide-n`
against a run on `reference-2n` and produce a table of differences that means
nothing.

### What it does not compare

Everything except metrics:

- not the timeline;
- not which segment diverged;
- not alarms — a run with six alarms and a run with none compare as identical
  if their metrics match;
- not transitions;
- not per-load service;
- not battery trajectories;
- not connection flows;
- not the snapshot or scenario hashes, so it will not tell you the two runs
  came from different topologies.

### The output that tells you nothing

Two of the experiments in this guide produce this:

```json
{"metric_differences": {}, "same_computation": false}
```

Every metric identical, hashes different. That happened for the resolution
change in chapter 15 and for the 1 ms failure shift on the redundant-pair
topology. The tool is telling you "these are not the same computation and I
cannot tell you why", and there is no follow-up command that will.

When you see it, the divergence is somewhere the comparison does not look:
timeline granularity, segment boundaries, alarm timing, telemetry, or the input
documents themselves. Chapter 15's segment-count table is how those two runs
were actually distinguished:

| Resolution | Timeline segments | Telemetry points |
|---:|---:|---:|
| 1,000 ms | 600 | 4,968 |
| 2,000 ms | 301 | 2,493 |

## The web explorer: *Compare runs*

Select two of the five fixtures and press *Compare runs*. Both run sequentially
and the results appear side by side. Comparing `REF-DC-N-001` with
`REF-DC-NP1-001`:

```text
Metric                     | A · Utility N loss…      | B · UPS R2 failure…
Demanded energy            | 166.67 kWh               | 266.67 kWh
Served energy              | 133.33 kWh               | 266.67 kWh
Unserved energy            | 33.33 kWh                | 0 kWh
Scenario service ratio     | 80%                      | 100%
Modeled redundancy state   | No path                  | Battery backed
Interruption duration      | 02:00                    | 00:00
Alarms                     | 4                        | 1
```

Plus a merged milestone table showing where the two runs diverge:

```text
Milestone                       | A       | B           | Alignment
UPS low-energy threshold · ups-n | T+04:24 | Not reached | Diverges
UPS depletion · ups-n            | T+05:00 | Not reached | Diverges
Restoration · utility-n          | T+07:00 | Not reached | Diverges
```

The milestone table is the better half. It aligns derived UPS transitions and
restorations across two runs, which is real analysis and is not available
anywhere else in the tool.

### Two cautions about that output

**The comparison above is not a meaningful one, and nothing said so.** Run A is
a 1 MW single-path topology; run B is a 1.6 MW N+1 topology. Their demanded
energies differ by 100 kWh — visible in the first row — and their service
ratios of 80% and 100% are therefore not comparable quantities. The explorer
presents them adjacent, in the same units, with no warning. It is very easy to
read "80% versus 100%" as a design comparison. It is not one.

**"Not reached" conflates two things.** `ups-n` does not exist in the N+1
topology at all, and the milestone table reports its transitions as "Not
reached" rather than "not present". A milestone that could never occur reads
the same as one that could have and did not.

## What you have to do by hand

For anything beyond the five metrics, you compare result files yourself. The
useful comparisons and how to build them:

### Where did the timelines diverge?

Walk both timelines and report the first segment whose state differs:

```python
"""Report the first timeline segment at which two runs diverge."""

import json
import sys

FIELDS = ("redundancy_state", "served_w", "unserved_w", "stranded_capacity_w")

left = json.load(open(sys.argv[1], encoding="utf-8"))["timeline"]
right = json.load(open(sys.argv[2], encoding="utf-8"))["timeline"]

for a, b in zip(left, right):
    if a["start_ms"] != b["start_ms"]:
        print(f"segment boundaries diverge at {a['start_ms']} vs {b['start_ms']} ms")
        break
    if any(a[f] != b[f] for f in FIELDS):
        print(f"state diverges at {a['start_ms']} ms")
        for f in FIELDS:
            if a[f] != b[f]:
                print(f"  {f}: {a[f]} -> {b[f]}")
        break
else:
    print(f"no divergence across {min(len(left), len(right))} compared segments")
```

```powershell
python diverge.py results/2n-feedloss.json results/2n-maint.json
```

```text
state diverges at 30000 ms
  redundancy_state: two_n -> single_path
```

That is the answer the maintenance-overlap analysis in chapter 7 actually
needed, and it took ten lines.

The same script also resolves the `metric_differences: {}` puzzle above. Point
it at the two resolution variants that `dc-twin compare` could not
distinguish:

```powershell
python diverge.py results/2n-res1000.json results/2n-res2000.json
```

```text
segment boundaries diverge at 1000 vs 2000 ms
```

There is the whole difference, in one line: the runs are physically identical
and cut into different segments.

### Which alarms differ?

```powershell
python -c "import json,sys; f=lambda p:{(a['time_ms'],a['code'],a['component_id']) for a in json.load(open(p))['alarms']}; a=f(sys.argv[1]); b=f(sys.argv[2]); print('only in A:', sorted(a-b)); print('only in B:', sorted(b-a))" results/2n-feedloss.json results/2n-maint.json
```

```text
only in A: []
only in B: [(30000, 'maintenance_active', 'pdu-b'), (168000, 'load_unserved', None)]
```

### Which load lost service?

No metric carries this. Reconstruct it from `timeline[].load_service_w` and
`demand_w`, per load, per segment.

## Discipline for comparisons

Whatever route you use, the same rules apply and none of them is enforced.

**Hold the horizon constant.** Every energy metric is an integral over the
horizon. Two runs with different horizons are not comparable on any energy
figure, and the tool will compare them without comment.

**Hold the demand profile constant.** The service ratio has demand in its
denominator. A design that serves less because it was asked for less scores
better.

**Hold the scenario constant when comparing designs**, and the design constant
when comparing scenarios. Change one thing. The chapter 5 comparison changes
only the topology; the chapter 6 battery comparison changes only
`usable_energy_mj`; the chapter 15 resolution experiment changes only
`resolution_ms`. Each is interpretable precisely because everything else is
pinned.

**Check the snapshot hashes before believing a comparison.** `dc-twin compare`
will not tell you the two results came from different topologies. Read
`snapshot_hash` from both files yourself:

```powershell
python -c "import json,sys; [print(p, json.load(open(p))['snapshot_hash']) for p in sys.argv[1:]]" results/a.json results/b.json
```

**Record what you changed.** Because the computation hash moves for cosmetic
edits as readily as for physical ones, the hash alone cannot tell you or anyone
else what the difference was. That has to come from you.

---

Previous: [15. Result hashes, determinism and replay](15-determinism-and-replay.md) ·
Next: [17. The reference scenarios](17-reference-scenarios.md)
