# 12. Reading alarms

There are exactly six alarm codes. They are annotations on the timeline, not a
diagnostic system, and the most important thing to know about them is when they
are *not* raised.

## The six codes

| Code | Severity | Raised when | Cleared by |
|---|---|---|---|
| `component_failed` | critical | a `component_failure` event fires | `component_restore` on the same component |
| `generator_start_failed` | critical | a `generator_start_failure` event fires | `generator_running` on the same generator |
| `maintenance_active` | info | a `maintenance_start` event fires | `maintenance_end` on the same component |
| `ups_low_energy` | warning | a discharging UPS crosses its threshold | never |
| `ups_energy_depleted` | critical | a discharging UPS reaches zero | never |
| `load_unserved` | critical | total unserved power is positive in the first solved state, or later goes from zero to positive | when total unserved returns to zero |

That is the complete set. There is no over-capacity alarm, no
approaching-rating alarm, no redundancy-lost alarm, no transfer alarm, and no
alarm for a component being isolated from the loads it serves.

## The alarm record

```json
{
 "id": "alarm-0005-ups-energy-depleted",
 "time_ms": 390000,
 "severity": "critical",
 "code": "ups_energy_depleted",
 "message": "ups-a exhausted its modeled usable battery energy.",
 "component_id": "ups-a",
 "causal_event_id": "system.ups_depleted.ups-a.390000"
}
```

Alarm IDs are sequential and self-describing: `alarm-NNNN-<code-with-hyphens>`.
Match on `code`, never on `message`; the message is human text that is not part
of the stable contract.

`component_id` is `null` for `load_unserved`, which is a system-level alarm.

## The alarm list is raise-only

The `alarms` array records raises. Clears live somewhere else entirely — in the
`transitions` array, as `alarms_cleared`:

```json
{"sequence": 7, "time_ms": 420000, "event_kind": "maintenance_end", "target_id": "pdu-b", "alarms_raised": [], "alarms_cleared": ["alarm-0001-maintenance-active"]}
{"sequence": 8, "time_ms": 422000, "event_kind": "atomic_transfer", "target_id": null, "alarms_raised": [], "alarms_cleared": ["alarm-0006-load-unserved"]}
```

Consequences:

- **The alarm count is not the number of problems.** It is the number of raises
  over the whole run, including ones that were resolved minutes earlier.
- **To know what was still active at the end**, you must walk the transitions
  and subtract every cleared ID from the raised set. Nothing does this for you.
- **The web explorer's events-and-alarms table shows raises only.** The
  composite run's two clearances do not appear anywhere in that table.

An alarm raised twice for the same reason is deduplicated: the ledger keys on
`code` plus component (or an explicit key for `load_unserved`), and re-raising
an already-active alarm returns the existing ID rather than creating a new one.
So a load that flickers in and out of service across many segments produces one
`load_unserved` alarm per outage, not one per segment.

## A complete alarm sequence

The composite reference run, all six alarms:

```text
  62000 ms  info     maintenance_active     pdu-b entered planned maintenance.
 120000 ms  critical component_failed       utility-a entered the modeled failed state.
 135000 ms  critical generator_start_failed generator-a failed its modeled start sequence.
 336000 ms  warning  ups_low_energy         ups-a reached its modeled low-energy threshold.
 390000 ms  critical ups_energy_depleted    ups-a exhausted its modeled usable battery energy.
 390000 ms  critical load_unserved          Modeled unserved load increased to 1600000 W.
```

Read as a narrative it is exactly right: planned work, then a utility loss,
then the generator that should have covered it failing, then the battery
warning, then the battery gone, then the load dropped. Every code carries its
`causal_event_id`, so each line traces back to either an authored event or a
derived milestone.

This is the alarm list working well. Now two cases where it does not.

## Trap one: a critical alarm with no service impact

Chapter 5's redundant-pair run — utility A fails at 60,000 ms on a 2N topology,
service never drops below 100%:

```text
  60000 ms  critical component_failed       utility-a entered the modeled failed state.
 141000 ms  warning  ups_low_energy         ups-a reached its modeled low-energy threshold.
 168000 ms  critical ups_energy_depleted    ups-a exhausted its modeled usable battery energy.
```

Two critical alarms and a warning. Service ratio: 1,000,000 ppm. Unserved
energy: 0 mJ. Interruption duration: 0 ms.

The battery genuinely drained to zero — that part is real, and chapter 5
explains why the solver preferred it over the live utility B. But nothing was
ever unserved, and `load_unserved` was correctly never raised. If you triage by
severity you will treat this run as worse than it was; if you triage by
`load_unserved` alone you will treat it as fine while a battery you were
counting on has silently emptied.

Neither reading is complete on its own. Alarms tell you what changed; metrics
tell you what it cost.

## Trap two: a run whose only alarm belongs to no event

This one is subtler, because the alarm you get points at nothing you wrote.

Chapter 14's stranded-capacity topology: a 1 MW load fed through a 600 kW PDU,
with a reserve cord left open. Run it healthy — no events at all:

```powershell
dc-twin run guide-strand.snapshot.json strand.scenario.json --output results/strand.json
```

```json
{
 "demanded_energy_mj": 600000000000,
 "interruption_count": 1,
 "interruption_duration_ms": 600000,
 "minimum_served_w": 600000,
 "modeled_redundancy_state": "partial_service",
 "peak_stranded_capacity_w": 400000,
 "served_energy_mj": 360000000000,
 "service_ratio_ppm": 600000,
 "unserved_energy_mj": 240000000000
}
```

400 kW unserved for the entire ten-minute horizon. 66.67 kWh of unmet demand. A
service ratio of 60%.

```text
-- segments 600, transitions 1, alarms 1, telemetry 4200
-- alarms
      0 ms  critical load_unserved          Modeled unserved load increased to 400000 W.
```

One alarm, at `0 ms`, and its `causal_event_id` is `system.initialized` — the
synthetic transition that records the first solved state. The scenario contains
no events at all, so there is no authored event to blame. The engine compares
its first solved state against a nominal fully served baseline, which is why a
run that is short from the first millisecond raises the alarm at `0 ms` rather
than staying silent for the whole horizon. The same now applies to chapter 4's
priority run, which starves a 300 kW load from `0 ms`.

The clear behaves normally from there. Close chapter 14's reserve cord at
120,000 ms and the transition at that time carries
`"alarms_cleared": ["alarm-0001-load-unserved"]`; in chapter 4's priority run
the same clear arrives when the lab load steps to zero.

Two things still do not follow from that alarm:

- **It says nothing about size or duration.** One raise covers a 1 W shortfall
  on one load and a total blackout equally. Only `unserved_energy_mj` and
  `interruption_duration_ms` distinguish them.
- **Nothing else about that run is alarmed.** 1.8 MW of source capacity is
  isolated from the unmet load for ten minutes and no code exists for it.

So the rule stands, in a weaker form:

> **Never conclude a run was healthy from a short alarm list.**
> Check `unserved_energy_mj` and `modeled_redundancy_state` first. The alarm
> list tells you that a condition exists, never how much it cost.

## Alarms are not a control system

Worth stating once, plainly. In this model an alarm:

- does not shed load;
- does not initiate a transfer;
- does not start a generator;
- does not change the allocation in any way;
- does not have an acknowledgement, an operator, a suppression rule, a
  priority queue, or a delivery mechanism;
- does not exist before the simulation and does not persist after it.

`ups_low_energy` in particular is often read as an actionable warning with time
in hand. Whether 54 seconds of remaining autonomy on the `guide-n` topology, or
six minutes on a larger battery, is "time in hand" is a judgement the model
cannot make and does not attempt. It raises the flag at the percentage you
specified and continues discharging.

## A checklist for reading alarms

1. Read `unserved_energy_mj` **before** the alarm list.
2. Count the raises, then walk `transitions[].alarms_cleared` to find what was
   still active at the horizon.
3. Match on `code`, not on `message`.
4. Treat `ups_energy_depleted` as a fact about a battery, not a fact about
   service. Check the timeline at that timestamp to see whether anything was
   lost.
5. Treat an empty alarm list as no information at all until you have checked
   the metrics.

---

Previous: [11. Reading the timeline](11-reading-the-timeline.md) ·
Next: [13. Unserved energy](13-unserved-energy.md)
