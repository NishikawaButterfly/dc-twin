# 18. Interpreting degraded and maintenance states

Most of a real analysis lives between "everything is fine" and "the room is
dark". This chapter is about reading that middle ground correctly, because
three of the seven states — `single_path`, `supported` and `battery_backed` —
all describe a fully served load, and they mean very different things.

## The states that still serve every watt

| State | Load fully served? | What is holding it up |
|---|---|---|
| `two_n` | yes | two qualifying paths, either alone sufficient |
| `single_path` | yes | exactly one qualifying path |
| `supported` | yes | non-battery capacity is sufficient, but no single path qualifies |
| `battery_backed` | yes | a battery is required; no non-battery path alone suffices |

All four report `unserved_w: 0`. A service ratio of 100% is compatible with
every one of them. If you triage runs by service ratio alone, these four
collapse into one.

## `single_path`: two different situations, one name

This is the state most likely to be misread, because it appears in two
completely different circumstances.

**A single-path design operating normally.** The `guide-n` and
`reference-n-plus-1` topologies report `single_path` from the first
millisecond, with everything healthy. Nothing has degraded; the design has one
source path and it is working.

**A redundant design that has lost a path.** The `guide-2n` topology reports
`two_n` until `pdu-b` enters maintenance at 30,000 ms, then `single_path`.
Something has degraded and the design is temporarily as exposed as one with no
redundancy.

The state value is identical in both cases. You cannot tell them apart from the
metric. You can only tell them apart by knowing the design and by reading the
transition into the state.

The practical rule: **read the transitions before reading the state.** A run
that opens on `single_path` is describing a design; a run that falls into
`single_path` is describing an event.

## `supported`: the state that usually means a labelling mistake

`supported` means non-battery capacity fully serves demand, but the graph
proves neither `two_n` nor `single_path`. In practice, on a well-formed
topology, this is rare — and when it appears it is usually chapter 5's
`path`-tag problem.

The demonstration: take the two-feed `guide-2n` topology and retag every
component `shared`. Nothing else changes.

```text
  worst state: supported
  segment 0 state: supported | sources: {"utility-a": 1000000, "utility-b": 0}
```

Two independent 1.2 MW utilities, each able to carry the whole load, reporting
`supported` forever because neither is tagged `A` or `B`.

If you see `supported` on a topology you believe is redundant, check the `path`
tags before you check anything else.

`supported` is also the honest answer for a topology whose redundancy genuinely
does not decompose into two source paths — several sources combining to serve a
load that none could carry alone, for instance. The model has no better name
for that, and it has no way to tell you whether losing any one of them would
matter.

## `battery_backed`: the state with a clock attached

`battery_backed` is the only state that is inherently time-limited. It says: a
battery is currently required, and no non-battery path could carry this alone.

Everything about it is fine until it is not. In the `REF-DC-2N-GEN-SUCCESS`
run, `battery_backed` lasts 15 seconds and ends with a generator picking up the
load. In `REF-DC-2N-001` it lasts 270 seconds and ends with the battery empty
and the room dark. The state name is identical; the outcome is not.

**Always read `battery_backed` together with the battery trajectory.** The
information you need is in the same timeline:

```text
--- segment 100000-101000  state=battery_backed
   source_power_w : {"ups-a": 1000000, "utility-b": 0}
   battery@end    : {"ups-a": 67000000000, "ups-b": 108000000000}
```

67,000,000,000 mJ remaining at 1,000,000 W is 67 seconds. Nothing in the
metrics tells you that; you compute it from the segment.

There is one further complication, from chapter 5: the state and the actual
allocation can disagree. In the redundant-pair feed-loss run the state read
`single_path` while UPS A was in fact carrying the entire load from battery.
The reported state and the `source_power_w` map are answering different
questions, and only the second tells you where the power came from.

The reliable test for "is a battery discharging right now" is not the state
name. It is whether a `ups-*` key appears in `source_power_w` with a positive
value.

## `partial_service`: a shortfall, not an outage

`partial_service` means some load is served and some is not. Given the
sequential allocation policy of chapter 4, the shortfall is concentrated: the
lowest-priority loads are starved completely while higher-priority loads are
untouched.

So `partial_service` typically does *not* describe everything running at
reduced power. It describes a subset of loads at zero. Which subset is only
visible in `load_service_w`.

Two runs in this guide sit in `partial_service` and neither is an outage in any
ordinary sense:

- Chapter 4's priority run: two of three loads fully served, one starved, for
  two minutes.
- Chapter 14's trap topology: one load at 60% of its demand for the entire
  horizon, because a downstream PDU is undersized.

Both are design findings. Neither would be described as "an interruption" by
anyone looking at the facility.

## Maintenance states

`maintenance` is not a distinct redundancy state. It is a component
availability value, and its consequence for the graph is identical to `failed`.
What differs is only the evidence trail:

| | `failed` | `maintenance` |
|---|---|---|
| Alarm code | `component_failed` | `maintenance_active` |
| Severity | `critical` | `info` |
| Cleared by | `component_restore` | `maintenance_end` |
| Excluded from the available network | yes | yes |
| Excluded from redundancy evidence | yes | yes |

Three interpretation rules follow.

**A maintenance window costs exactly what a failure costs.** Chapter 7's
overlap run makes the point: 20 kWh unserved and 72 seconds dark, caused by a
utility failure that would have cost nothing had `pdu-b` been available. The
model does not discount planned outages.

**An `info` alarm can be the most consequential line in the log.** In that run
the `maintenance_active` alarm at 30,000 ms is `info` severity and is the
reason the whole thing went dark. Severity in this model reflects the *kind* of
event, not its consequence.

**`maintenance_end` does not mean service restored.** It means the component is
back. Whether the load is served again depends on connection positions.
Compare:

- `guide-2n` maintenance overlap: both cords stayed closed throughout, so
  restoring `pdu-b` at 240,000 ms restored service in the same millisecond.
- `REF-DC-2N-001`: the B cords had been opened by a transfer at 62,000 ms, so
  `maintenance_end` at 420,000 ms restored nothing and the room stayed dark for
  another two seconds until the transfer at 422,000 ms.

If you are modelling a real maintenance procedure, that two-second gap is the
part worth getting right, and it comes entirely from events you author.

## Reading a degraded run: a procedure

1. **Find the transitions.** They are the shortest summary of what happened.
2. **Classify each state change** as entering or leaving degradation, using the
   design as context. `single_path` at `0 ms` is a design; `single_path` at
   `30000 ms` is an event.
3. **For any `battery_backed` window, compute the remaining time** from
   `battery_energy_mj` and the UPS's `source_power_w`. That number is the one
   that matters and no metric reports it.
4. **For any `partial_service` window, read `load_service_w`** to find which
   loads were starved. The aggregate figures will not tell you.
5. **Check `source_power_w` for `ups-*` keys** in every segment, regardless of
   the reported state. That is the only reliable indicator that a battery is
   discharging.
6. **Only then read the run-level `modeled_redundancy_state`**, remembering it
   is the worst state over any non-zero duration and may describe one second of
   a ten-minute run.

---

Previous: [17. The reference scenarios](17-reference-scenarios.md) ·
Next: [19. What conclusions may be drawn, and what may not](19-conclusions.md)
