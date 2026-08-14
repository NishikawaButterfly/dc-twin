# 9. Creating a scenario

A scenario is a small document. Getting it right is mostly about three
decisions: the horizon, the resolution, and what you choose to leave out.

## The envelope

```json
{
  "schema_id": "dc-twin.scenario",
  "schema_version": "1.0.0",
  "scenario_id": "GUIDE-2N-MAINT-OVERLAP",
  "label": "PDU B maintenance window overlapping a utility A failure",
  "snapshot_id": "guide-2n",
  "horizon_ms": 600000,
  "resolution_ms": 1000,
  "data_classification": "synthetic",
  "events": [ ... ]
}
```

Nine fields, all required, no others accepted. `snapshot_id` must match the
snapshot you run it against, and the mismatch is caught before anything else
happens:

```json
{"detail": "Invalid value at $.snapshot_id: does not match the supplied design snapshot", "error_code": "contract.invalid_field"}
```

A scenario is therefore bound to one topology. To run "the same failure on two
designs", as chapter 5 does, you write two scenario files that differ only in
`snapshot_id` and `scenario_id`. There is no way to parameterise one scenario
across topologies.

`label` is free text up to 160 characters and appears in the API catalog, the
web explorer and the result envelope. `scenario_id` must match the stable
identifier syntax: alphanumeric start, then letters, digits, `.`, `_`, `:` or
`-`, up to 64 characters.

## Choosing the horizon

`horizon_ms` runs from 1 ms to 604,800,000 ms (seven days). It is a hard
boundary in both directions: nothing is simulated past it, and every event must
fall within it.

```json
{"detail": "Invalid value at $.events[0].time_ms: must be an integer from 0 through 600000", "error_code": "contract.invalid_field"}
```

The horizon is also where a scenario silently ends rather than resolves. In the
chapter 5 single-feed run, the utility fails at 60,000 ms and is never
restored; the run reports 432,000 ms of interruption, which is simply "from
depletion until the horizon ran out". Extend the horizon to an hour and the
unserved energy grows proportionally, without anything about the design
changing.

That makes the horizon an input to every energy metric, and a lever you can
pull without noticing. Two runs with different horizons are not comparable on
any energy figure, and are barely comparable on a service ratio.

Pick the horizon to cover the story you are telling, from a stable state before
the first event to a stable state after the last, and keep it identical across
any set of runs you intend to compare.

## Choosing the resolution

`resolution_ms` runs from 1 ms to the horizon. It controls how finely the
timeline is cut into reported segments. It does **not** control the accuracy of
the simulation.

This is worth being blunt about, because the field name invites the opposite
assumption. The engine always splits intervals at every event time, every
derived UPS milestone, and the horizon. Battery depletion is computed at the
exact integer millisecond regardless of resolution. Resolution adds *additional*
reporting boundaries on top of those.

The proof is a run. Take the chapter 5 redundant-pair scenario, change
`resolution_ms` from 1000 to 2000, change nothing else, and compare:

```powershell
dc-twin compare results/2n-res1000.json results/2n-res2000.json
```

```json
{"left_run_id": "run-0ca87f32ca8385a8", "metric_differences": {}, "right_run_id": "run-13fccca12e0489f5", "same_computation": false}
```

Every metric is identical. What changed is the output size:

| Resolution | Timeline segments | Telemetry points |
|---:|---:|---:|
| 1,000 ms | 600 | 4,968 |
| 2,000 ms | 301 | 2,493 |

So resolution buys you timeline granularity and costs you output size. Choose
it for the resolution at which you want to *read* the run, not for accuracy you
think you are gaining.

### The resolution ceiling

Fine resolution runs into the bounded envelope quickly. The parser estimates
the segment count before simulating and refuses anything that would exceed
10,000 timeline segments:

```powershell
dc-twin validate-scenario guide-n.snapshot.json bad/resolution.scenario.json
```

```json
{"detail": "Scenario would exceed 10000 timeline segments.", "error_code": "contract.timeline_limit"}
```

That was a 600,000 ms horizon at 1 ms resolution. The estimate is:

```text
segments ≈ ceil(horizon_ms / resolution_ms) + event_count + 2 * ups_count
```

There is a parallel limit on telemetry, at 250,000 points, where the points per
segment are `4 + ups_count + load_count + source_count`. A topology with many
loads hits the telemetry ceiling before the segment ceiling.

The practical envelope, measured on the single-UPS `guide-n` topology with one
event: a 600,000 ms horizon accepts 61 ms and rejects 60 ms. A seven-day
horizon accepts 61,000 ms and rejects 60,000 ms. So the finest useful
resolution is a little over one ten-thousandth of the horizon, and if you need
millisecond detail across a long window you cannot have it in one run.

## Authoring the events

Chapter 7 covers the eight kinds. Three habits are worth adopting.

**Name events for what they are and when.** The bundled scenarios use
`event-003-utility-a-failure`. The sequence prefix keeps the array readable and
the descriptive suffix survives into the alarm records, where `causal_event_id`
points back at it. When you read a timeline segment six months later,
`causal_event_ids: ["event-004-generator-a-start-failure"]` tells you
everything; `causal_event_ids: ["e4"]` tells you nothing.

**Write the response events, not just the fault events.** The model does
nothing automatically. A scenario containing only failures is a scenario in
which nobody responds, which is a legitimate thing to model as long as you know
that is what you modelled.

**Leave a stable tail.** End the scenario some time after the last event so the
final state is visible for more than one segment. It makes the timeline readable
and it keeps the last segment from being an artefact of where the horizon fell.

## Validate before you run

```powershell
dc-twin validate-scenario guide-2n.snapshot.json maint-overlap.scenario.json
```

```json
{"hash": "da0c3b24bfd8e28a975b7150e925241952b7d4c15696a8e0f43add2c933aa2c3", "scenario_id": "GUIDE-2N-MAINT-OVERLAP", "valid": true}
```

The returned hash is the SHA-256 of the canonical scenario JSON, and it appears
as `scenario_hash` in every result produced from it.

What validation checks: document shape, field types and ranges, identifier
syntax, unknown fields, duplicate JSON keys, duplicate IDs, references to
components and connections that exist, event kinds matched to target kinds,
load steps within rating, generator timing rules, contradictory same-timestamp
events, horizon bounds, and the resource envelope.

What validation does not check: anything that depends on simulated state. The
paralleling case in chapter 8 validates cleanly and fails at run time. Treat
`validate-scenario` as a fast syntax and reference check, not as a guarantee.

## The scenario you cannot write

For completeness, since these are the requests that come up:

- **No repeating or recurring events.** Every occurrence is a separate entry.
- **No conditional events.** Nothing fires "if the battery drops below 20%".
  The derived UPS milestones are the only internally generated transitions, and
  you cannot attach anything to them.
- **No randomness or seeds.** The engine is deterministic by design; there is
  no distribution to sample and no Monte Carlo driver.
- **No parameter sweeps.** One file, one run.
- **At most 1,000 external events** per scenario.

---

Previous: [8. Transfers](08-transfers.md) ·
Next: [10. Running a scenario](10-running-a-scenario.md)
