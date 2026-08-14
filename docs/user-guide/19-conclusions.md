# 19. What conclusions may be drawn, and what may not

This is the chapter to read before a dc-twin figure goes into anything anyone
else will act on.

The engine is exact. It will reproduce a result byte for byte on another
machine, and it will reproduce a *wrong* result with exactly the same fidelity.
Nothing in the output distinguishes a well-founded run from a badly founded
one. That discrimination is entirely yours, and this chapter is about how to
make it.

## The three questions a run can answer

dc-twin answers exactly three kinds of question well:

1. **Connectivity.** Given this graph in this state, can source capacity reach
   this load? This is what the tool is: a reachability and capacity
   bookkeeper, and it is rigorous at it.
2. **Timing.** Given this stored energy and this draw, when does the battery
   run out, and does that happen before or after the event you scheduled? The
   arithmetic is exact integer division and checkable by hand.
3. **Relative comparison under a fixed scenario.** Given two designs subjected
   to the identical event sequence over the identical horizon with the
   identical demand profile, which loses less energy? Chapter 5's N-versus-2N
   pair is the model case.

Everything defensible you will ever say from a dc-twin run is a form of one of
those three. If your sentence is not one of them, stop and check it against
this chapter.

## The same run, two conclusions

Take the maintenance-overlap run from chapter 7. `guide-2n`, a 600,000 ms
horizon, a 1 MW dual-cord load, PDU B in maintenance from 30,000 ms to
240,000 ms, utility A failing at 60,000 ms and never restored.

```text
      0 ms  two_n           served= 1000000 unserved=       0 stranded=       0
  30000 ms  single_path     served= 1000000 unserved=       0 stranded=       0
  60000 ms  battery_backed  served= 1000000 unserved=       0 stranded=       0
 168000 ms  no_path         served=       0 unserved= 1000000 stranded= 1000000
 240000 ms  single_path     served= 1000000 unserved=       0 stranded=       0
```

| Metric | Value |
|---|---:|
| Unserved energy | 72,000,000,000 mJ (20.0 kWh) |
| Service ratio | 880,000 ppm (88%) |
| Interruption duration | 72,000 ms |
| Worst modeled state | `no_path` |
| Peak stranded capacity | 1,000,000 W |

### A sound conclusion

> In this model, with the stated ratings and a 30 kWh UPS, a loss of utility A
> occurring 30 seconds into a PDU B maintenance window results in 72 seconds of
> fully unserved load and 72,000,000,000 mJ (20.0 kWh) of unserved demand,
> beginning when UPS A depletes at 168,000 ms and ending when the maintenance
> window closes at 240,000 ms. Throughout that period utility B remained
> available with 1.2 MW that the model could not route to the load, reported as
> 1,000,000 W of stranded capacity. The identical utility failure with no
> maintenance window in progress produced no unserved energy at all
> (`GUIDE-2N-FEED-LOSS`, computation hash `0ca87f32…`).
>
> The exposure is therefore governed by the relationship between the battery
> autonomy and the maintenance window duration, both of which are inputs.

Why it holds:

- It says "in this model" and names the inputs it depends on.
- Every number is the exact integer, with the kWh conversion marked as a
  conversion.
- The mechanism is stated, so a reader can check it: depletion at 168,000 ms,
  window closing at 240,000 ms.
- The comparison is against a run that differs in exactly one thing, and it is
  identified by hash.
- The closing sentence names what actually drives the result — two inputs the
  author chose — rather than presenting it as a property of the facility.

### An unsound conclusion, from the same run

> The design has 88% availability and cannot survive a utility failure during
> maintenance. A 20 kWh loss would take the load down for 72 seconds.

Every clause is wrong, and each in a different way.

**"88% availability".** The service ratio is served energy over demanded energy
for one invented ten minutes. Availability is a long-run frequency built from
failure rates and repair times. dc-twin has no failure rate, no repair time, no
probability of any kind, and no annual denominator. The two numbers share no
units and no meaning. Extend the horizon to twenty minutes without changing
anything else and the same design reports a different figure.

**"cannot survive".** The model was told what failed and when. It did not
discover a vulnerability; it computed the consequence of one scenario the
author wrote. A different maintenance window, a different failure time, or a
larger battery produces a different answer, and none of those is more or less
"the truth" about the design.

**"a 20 kWh loss".** The figure is 20 kWh *of unserved demand within this
600,000 ms horizon*. It is not an energy cost, not a financial loss, and not a
bounded quantity — the horizon ended while the situation was still resolving in
the first-feed variant. Quote the horizon or do not quote the number.

**"take the load down for 72 seconds".** This is the closest to defensible and
still fails. In the model the load's demand goes unserved for 72 seconds.
Whether real equipment goes down depends on internal power supplies, hold-up
capacitance, ride-through, and what the load actually is — none of which
exists in this model. The model ends at the load's terminal node.

**And the sentence omits the finding that mattered.** Nothing in it mentions
that 1.2 MW of healthy utility capacity was sitting unreachable for the whole
outage. That is the actionable result of the run, and the availability framing
buried it.

## A second pair: the run that looks perfect

Chapter 5's redundant-pair feed loss. `guide-2n`, utility A fails at 60,000 ms,
never restored.

| Metric | Value |
|---|---:|
| Unserved energy | 0 mJ |
| Service ratio | 1,000,000 ppm (100%) |
| Interruption duration | 0 ms |
| Worst modeled state | `single_path` |
| Alarms | 3, of which 2 critical |

### Unsound

> The 2N design rides through a utility failure with no impact.

### Sound

> In this model the load remained fully served for the entire horizon after
> utility A failed. However, the allocation drew the full 1 MW from UPS A's
> battery rather than from the available utility B feed, discharging it from
> 108,000,000,000 mJ to zero between 60,000 ms and 168,000 ms and raising
> `ups_low_energy` at 141,000 ms and `ups_energy_depleted` at 168,000 ms.
> Utility B delivered 0 W throughout that period and picked the load up only
> after the battery was exhausted.
>
> This is a modelling artefact of the max-flow allocation preferring the
> shortest path from source to load, not a prediction of how a real dual-cord
> load would draw. It does mean the run should not be cited as evidence that
> the battery was preserved.

The 100% service ratio and the 0 mJ unserved energy are both true. Reading only
those two numbers, you would file this run as a clean pass and miss that a
battery you were counting on emptied itself. The two critical alarms are the
only thing in the output that points at it, and chapter 12 shows that alarms
are just as capable of pointing at nothing.

## Conclusions you may draw

Phrase them like this, and they hold:

- "In this model, under scenario X on snapshot Y, the load was fully served for
  the entire horizon."
- "Under this scenario, design A loses 20.0 kWh where design B loses none."
- "The modelled battery autonomy at this draw is 108 seconds, so a restoration
  later than 168,000 ms leaves the load unserved."
- "In the normal configuration the model reports 400,000 W of stranded
  capacity, indicating source capacity that cannot reach the load before any
  failure occurs."
- "This result is reproducible: computation hash `5ae8c11939145806…` on engine
  1.0.0."
- "The redundancy evidence for this segment is `single_path`, meaning exactly
  one tagged source path could serve the total demand alone in this graph
  state."

Each names the model, the scenario, and the exact quantity, and each is checkable
by anyone with the two input files.

## Conclusions you may not draw

### About availability and reliability

You may not derive availability, uptime, an SLA figure, MTBF, MTTR, a failure
probability, an expected annual downtime, or a risk score. There is no
probability anywhere in this engine. A service ratio is one deterministic run
over one horizon.

### About certification and compliance

You may not derive an Uptime Institute Tier, a concurrent-maintainability
finding, a fault-tolerance classification, or compliance with any code or
standard. The state name `two_n` is a graph observation about two tagged source
paths at one instant.

Chapter 5's shared-bus run is the demonstration to keep in mind: a topology
reporting `two_n` for two minutes, taken entirely dark by one component
failure, with both utilities still healthy. No Tier framework would call that
2N. The model does, because the model's `two_n` means something narrower than
the industry term that it borrows.

### About electrical behaviour

You may not derive fault current, interrupting duty, protection settings,
selectivity, arc-flash energy, voltage drop, harmonic distortion, transformer
loading in kVA, power factor, transient stability, or anything requiring
voltage, current or impedance. None of those quantities exists in the model.

You may not conclude that a modelled transfer is safe, permissible, or
physically achievable. The ATS paralleling guard is a contract check on one
modelling rule, not a switching study. A transfer that would be catastrophic
executes silently at any node that is not an ATS or STS.

### About equipment and loads

You may not conclude that equipment would survive, trip, ride through, or
restart. You may not conclude that a load was "lost" — only that its demand
went unserved in the model. You may not conclude anything about cooling, which
does not exist here, or about the thermal consequences of a power interruption.

### About real facilities

You may not conclude anything about a real site. Every fixture is synthetic and
the parser will only accept `data_classification: "synthetic"`. Even with real
ratings, the model would remain a lossless active-power capacity abstraction.

### About the flows in the timeline

You may not read `connection_flow_w` as predicted current, cable loading, or
metering. Chapter 3's demonstration is unambiguous: two symmetric closed cords
on a healthy dual-cord load, and the model put 1,000,000 W on one and 0 W on
the other. The allocation is feasible, not physical.

### About what the alarm list means

You may not conclude a run was healthy because it raised no alarms. Chapter
14's trap topology serves 60% of its load for a full ten minutes and raises
zero alarms, because the condition was true from the first millisecond and
`load_unserved` requires a transition.

## The inputs that decide everything

The rule from chapter 1, now in operational form. Four inputs dominate every
result, and the model has no way to validate any of them:

**Component and connection ratings.** These are integers you typed. If a rating
is nameplate where it should be derated, or continuous where it should be
short-time, the model has no opinion. A path with headroom absorbs an error
invisibly and then fails completely just past the threshold — the failure mode
is a cliff, not a slope.

**Load demand.** Constant per interval, exactly what you declared. Real IT load
varies, has diversity, and has inrush. None of that is representable.

**UPS usable energy.** The single most consequential number in most runs,
because it sets the battery clock that most outcomes turn on. It is a figure
you supplied and it should already account for everything the model does not
have: end-of-discharge limits, aging, temperature, the difference between
nameplate and usable, and the discharge rate. If it does not, the depletion
time is precise and wrong.

**Event times.** Every response in the model is an event you authored. The
generator start delay is a validation floor, not a modelled process. "The
system recovered in 15 seconds" is always a restatement of a 15-second delay
you typed.

## Before you quote a run

A short checklist. It takes two minutes and it is the difference between an
analysis and a liability.

1. **Did I check `unserved_energy_mj` before the alarm list?** An empty alarm
   list means nothing on its own.
2. **Is the horizon long enough that the situation resolved?** If the run ended
   mid-outage, the unserved figure is a floor set by where I stopped the clock.
3. **Am I comparing runs with the same horizon, the same demand profile and
   one deliberate difference?** If not, the comparison is not one.
4. **Did I check the snapshot hashes of both results?** `dc-twin compare` will
   not tell me they came from different topologies.
5. **Does any `battery_backed` or `single_path` window hide a battery that was
   actually carrying the load?** Check `source_power_w` for `ups-*` keys.
6. **Have I stated the horizon, the scenario ID, the snapshot hash and the
   computation hash alongside the number?**
7. **Does my sentence contain the words "availability", "Tier", "uptime",
   "SLA", "safe", "will", or "would survive"?** If so, it almost certainly
   overreaches.
8. **Would the sentence still be true if I had chosen a different failure time
   by one minute?** If not, say so — that sensitivity is the finding.

## What the tool is genuinely good for

Ending on the positive case, because the boundaries above are not a reason to
avoid the tool.

dc-twin is very good at making an event-ordering argument explicit and
checkable. The race between a battery clock and a restoration clock is real,
consequential, and usually reasoned about informally. This tool turns it into
integer arithmetic that another engineer can verify with a calculator and
reproduce with a hash.

It is very good at exposing isolation. Chapter 14's trap topology — 1.8 MW of
source capacity idle while 400 kW goes unserved, in the normal configuration,
with no alarms — is exactly the kind of thing a single-line diagram hides and
one healthy run reveals.

And it is very good at forcing a scenario to be written down. The discipline of
having to author every response event, at a specific millisecond, is itself
valuable. A scenario nobody can write down is usually a scenario nobody has
thought through.

Those are real contributions. They are just not the contributions the metric
names suggest, which is why this chapter exists.

---

Previous: [18. Degraded and maintenance states](18-degraded-states.md) ·
Next: [20. Troubleshooting](20-troubleshooting.md)
