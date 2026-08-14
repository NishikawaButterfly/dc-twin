# 7. Events, failures and maintenance windows

A scenario is a horizon, a resolution, and a list of timestamped events. The
events are the only thing that ever changes state. This chapter covers the
eight event kinds, the ordering rules that make equal-time events
deterministic, and the specific behaviour of maintenance windows.

## The eight event kinds

| Kind | Target | Required extra field | Effect |
|---|---|---|---|
| `component_failure` | any component | `"status": "failed"` | Component leaves the graph; `critical` alarm |
| `component_restore` | any component | `"status": "available"` | Component returns; clears its failure alarm |
| `maintenance_start` | any component | `"status": "maintenance"` | Component leaves the graph; `info` alarm |
| `maintenance_end` | any component | `"status": "available"` | Component returns; clears its maintenance alarm |
| `generator_running` | a generator | `"status": "available"` | Generator becomes an eligible source |
| `generator_start_failure` | a generator | `"status": "failed"` | Generator fails; `critical` alarm |
| `atomic_transfer` | connections | `open_connection_ids`, `close_connection_ids` | Connections change position as one transition |
| `load_step` | a load | `demand_w` | Load demand changes |

The `status` field is redundant with the kind and is checked for consistency —
`component_failure` must carry `"status": "failed"`, and so on. It exists so
that a scenario file reads unambiguously without knowing the kind semantics.

## Ordering: the rule that makes a scenario reproducible

Events at the same timestamp execute in a fixed order, by semantic priority and
then by event ID:

| Priority | Kinds |
|---:|---|
| 10 | `component_failure`, `generator_start_failure` |
| 20 | `maintenance_start` |
| 30 | `component_restore`, `maintenance_end` |
| 35 | `generator_running` |
| 40 | `atomic_transfer` |
| 50 | `load_step` |

**JSON array order is irrelevant.** The parser sorts events by
`(time_ms, semantic_priority, id)` before simulation. You can shuffle the array
in the file and get the same result — though not the same scenario hash, since
the hash covers the document as written.

The ordering is deliberately pessimistic: losses land before restorations, so a
scenario that fails and restores the same component in the same millisecond
resolves to the safe interpretation. In practice you cannot write that anyway,
because contradictory events are rejected:

```json
{"detail": "Multiple events target utility-a at 60000 ms.", "error_code": "scenario.contradictory_events"}
```

One component, one event, per timestamp. Transfers are exempt from that rule
because they target connections rather than components.

### Service is evaluated after the whole group

Equal-time events are applied as a group and service is re-evaluated once, at
the end of the group. This is why the bundled `reference-n-plus-1` scenario can
fail UPS R2 and close the reserve output at the same instant without recording
a momentary loss: both events land, then the allocation runs.

If the engine had evaluated after each event individually, that scenario would
have shown an interruption of zero duration, and every metric that counts
transitions would have been polluted by an artefact of authoring order.

## Failures

A `component_failure` is a declaration, not a detection. It says: at this
millisecond, treat this node as absent. Nothing caused it, nothing sensed it,
and nothing else responds to it automatically. If a failure should trigger a
transfer, you must author the transfer event yourself, at the timestamp you
believe it would occur.

That last point is the whole discipline of scenario authoring. The model will
not close a tie breaker for you, will not start a generator for you, and will
not shed a load for you. Every response is an input you decided on, which means
every "the system recovered in 15 seconds" result is a restatement of a
15-second delay you typed.

## Generators, and the two rules that constrain them

A generator is inert until a `generator_running` event fires. Setting
`initial_status: "available"` does not energise it; an available standby
generator is available *to be started*, not running.

Version 1 models **reactive starts only**, and enforces it:

```powershell
dc-twin validate-scenario examples/synthetic/reference-2n.snapshot.json proactive.scenario.json
```

```json
{"detail": "Event event-001-generator-a-running has no preceding same-path utility failure in v1.", "error_code": "scenario.generator_without_source_loss"}
```

Every `generator_running` or `generator_start_failure` must be preceded by a
`component_failure` on a **utility on the same path**. You cannot model a
pre-emptive start ahead of a storm, a scheduled load-bank test, a peak-shaving
run, or a generator started for any reason other than losing its own path's
utility.

The second rule is the start delay:

```json
{"detail": "Event event-002-generator-a-running occurs after 10000 ms, below generator-a's 15000 ms start delay.", "error_code": "scenario.generator_start_too_early"}
```

The outcome must be at least `start_delay_ms` after the latest qualifying
utility loss. The delay is a floor, not a schedule: nothing fires
automatically at `t + start_delay_ms`. If you never write the outcome event,
the generator never starts and the scenario simply runs without it.

Note what `start_delay_ms` is not. It is not a modelled cranking sequence, not
a load-acceptance ramp, and not a block-loading limit. A generator that reaches
`generator_running` is instantly a full-rating source. There is no step-load
behaviour, no frequency excursion, no time to accept load.

## Maintenance windows

`maintenance_start` and `maintenance_end` set and clear the `maintenance`
availability state. Inside the capacity solver, `maintenance` and `failed` are
identical: the component is excluded from the available network, carries no
flow, and cannot be traversed.

The differences are entirely in evidence:

| | `failed` | `maintenance` |
|---|---|---|
| Alarm code | `component_failed` | `maintenance_active` |
| Alarm severity | `critical` | `info` |
| Cleared by | `component_restore` | `maintenance_end` |
| Effect on flow | excluded | excluded |
| Effect on redundancy evidence | excluded | excluded |

Two practical consequences:

**A maintenance window costs you exactly what a failure would.** Putting a path
into maintenance during a run removes it from redundancy evidence for the whole
window. There is no notion of "concurrently maintainable" here — the model has
one way to take a component out and one consequence for doing so.

**Ending maintenance does not restore service by itself.** It restores the
*component*. Whether the load is served again depends on whether a closed,
available path now reaches it. Which brings us to the interesting case.

## A maintenance window that overlaps a failure

This is the scenario worth constructing deliberately, because it is where the
model earns its keep. Take `guide-2n` from chapter 3 and write:

```json
"events": [
  { "id": "event-001-pdu-b-maintenance-start", "time_ms": 30000,
    "kind": "maintenance_start", "component_id": "pdu-b", "status": "maintenance" },
  { "id": "event-002-utility-a-failure", "time_ms": 60000,
    "kind": "component_failure", "component_id": "utility-a", "status": "failed" },
  { "id": "event-003-pdu-b-maintenance-end", "time_ms": 240000,
    "kind": "maintenance_end", "component_id": "pdu-b", "status": "available" }
]
```

Path B goes out for planned work, and thirty seconds later the *other* path
loses its utility.

```powershell
dc-twin run guide-2n.snapshot.json maint-overlap.scenario.json --output results/maint.json
```

```text
      0 ms  two_n           served= 1000000 unserved=       0 stranded=       0
  30000 ms  single_path     served= 1000000 unserved=       0 stranded=       0
  60000 ms  battery_backed  served= 1000000 unserved=       0 stranded=       0
 168000 ms  no_path         served=       0 unserved= 1000000 stranded= 1000000
 240000 ms  single_path     served= 1000000 unserved=       0 stranded=       0
```

```text
  30000 ms  info     maintenance_active     pdu-b entered planned maintenance.
  60000 ms  critical component_failed       utility-a entered the modeled failed state.
 141000 ms  warning  ups_low_energy         ups-a reached its modeled low-energy threshold.
 168000 ms  critical ups_energy_depleted    ups-a exhausted its modeled usable battery energy.
 168000 ms  critical load_unserved          Modeled unserved load increased to 1000000 W.
```

| Metric | Value |
|---|---:|
| Demanded energy | 600,000,000,000 mJ (166.666667 kWh) |
| Served energy | 528,000,000,000 mJ (146.666667 kWh) |
| Unserved energy | 72,000,000,000 mJ (20.000000 kWh) |
| Service ratio | 880,000 ppm (88%) |
| Interruption duration | 72,000 ms |
| Interruption count | 1 |
| Peak stranded capacity | 1,000,000 W |
| Worst modeled state | `no_path` |

Compare it to chapter 5. **The identical utility failure, on the identical
topology, cost nothing when path B was available and cost 20 kWh and 72 seconds
of darkness when path B was in maintenance.** The maintenance window did not
cause the failure and did not make the failure worse; it removed the thing that
would have absorbed it.

Three details in that run are worth noticing.

**The battery clock is unchanged.** UPS A still depletes at exactly 168,000 ms,
because the arithmetic depends only on stored energy and discharge power, both
of which are the same as in the chapter 5 run. What changed is what was waiting
on the other side of depletion.

**Service returns at 240,000 ms with no transfer event.** Both cords were
closed from the start and were never opened, so restoring `pdu-b` is
sufficient. Contrast this with the bundled `REF-DC-2N-001` scenario, where the
loads had been transferred away from path B by an explicit event: there,
`maintenance_end` at 420,000 ms restored the component and service stayed dark
for another two seconds until a second transfer event at 422,000 ms closed the
B cords. Whether recovery is automatic in the model depends entirely on
whether you opened anything.

**Stranded capacity appears at 168,000 ms.** Utility B is available with 1.2 MW
throughout, and it cannot reach the load while `pdu-b` is out. Chapter 14
covers the figure.

## Choosing the window

If you want to use dc-twin to reason about maintenance risk, the useful
experiment is not one run but a sweep: hold the failure fixed and move the
maintenance window, or hold the window fixed and move the failure. The engine
has no facility for that — there is no sweep, no parameter sensitivity mode and
no batch driver. You author each scenario file and run each one. Chapter 16
covers what you can and cannot do with the results afterwards.

---

Previous: [6. UPS batteries and runtime](06-ups-and-runtime.md) ·
Next: [8. Transfers](08-transfers.md)
