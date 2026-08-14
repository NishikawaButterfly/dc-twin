# 6. UPS batteries and runtime

The battery is the only part of this model with memory. Everything else is
recomputed from the current state each interval; stored energy carries forward,
and it is what turns a topology question into a timing question.

## What a UPS is in this model

A `ups` component has three fields beyond the common ones:

| Field | Meaning | Range |
|---|---|---|
| `capacity_w` | Maximum throughput, whether passing upstream power or supplying from battery | 1 to 10,000,000,000 |
| `usable_energy_mj` | Initially stored, usable energy | 1 to 10<sup>18</sup> |
| `low_energy_threshold_pct` | Integer percentage at which a warning is raised | 1 to 99 |

Note that one rating governs both modes. There is no separate inverter rating,
no bypass rating, no overload rating, and no distinction between what the unit
can pass through and what it can supply from battery.

## The eligibility rule

This is the rule to memorise:

> A UPS passes upstream power while an available utility or running generator
> can energise it through the current closed, available graph. It becomes a
> **finite battery source** only when no such non-battery source can reach it
> upstream, its own state is `available`, and its stored energy is positive.

Eligibility is not dispatch. An eligible battery only discharges for demand
that no live source can reach, because the allocation of chapter 4 offers the
live sources first and the batteries second. An eligible UPS that is never
called on appears in `source_power_w` at `0 W` and ends the run with its energy
untouched.

Four consequences, each of which surprises someone:

**A UPS does not discharge because the load lost power.** It discharges because
*it* lost its upstream feed. In the shared-bus run from chapter 5, a single
component failure downstream took the entire 1 MW load to zero for three
minutes, and both UPS units finished the run at their full
108,000,000,000 mJ. Their own feeds were fine, so neither was eligible, and
neither noticed the load was dark.

**A UPS that is upstream-energised contributes no battery capacity at all.**
It is a pass-through node with a rating. It is not "supporting" anything.

**An islanded UPS does not necessarily discharge.** In chapter 5's
redundant-pair feed loss, UPS A loses its own upstream feed at 60,000 ms and is
eligible for the rest of the run, and it delivers nothing: utility B reaches
the load through path B, and stored energy is only reached for when no live
source can. Eligibility tells you a unit *could* supply; `source_power_w` tells
you whether it did.

**A failed UPS is not a bypass.** Setting a UPS to `failed` removes the node
entirely; power does not route around it. If your real design has a maintenance
bypass, you must model it as a separate connection that skips the UPS node, and
then open and close it with transfer events.

There is no charging in version 1. Once discharged, energy never returns.
Restoring the upstream utility stops the discharge but does not refill the
battery — the stored value simply stays where it stopped.

## Runtime arithmetic

Within an interval every quantity is constant, so the debit is exact:

```text
battery_debit_mj = battery_output_w * interval_duration_ms
```

The engine derives two milestone times for each discharging UPS and splits the
interval at the exact integer millisecond so that the alarm, the energy debit
and the service change all land on the same boundary.

For a UPS with `usable_energy_mj = E`, `low_energy_threshold_pct = P`,
discharging at a constant `W` watts from time `t₀`:

```text
threshold_mj = E * P // 100
low_energy_time  = t₀ + (E - threshold_mj) / W
depletion_time   = t₀ + E / W
```

Note `//`: the threshold uses integer floor division, so a threshold that does
not divide evenly rounds down.

### Worked against a real run

The `guide-n` UPS holds 30 kWh and the load is 1 MW:

```text
E = 30 kWh = 30 * 3,600,000,000 = 108,000,000,000 mJ
W = 1,000,000 W
t₀ = 60,000 ms   (the utility fails)

threshold_mj    = 108,000,000,000 * 25 // 100 = 27,000,000,000 mJ
low_energy_time = 60,000 + (108,000,000,000 - 27,000,000,000) / 1,000,000
                = 60,000 + 81,000 = 141,000 ms
depletion_time  = 60,000 + 108,000,000,000 / 1,000,000
                = 60,000 + 108,000 = 168,000 ms
```

And the engine, run against that snapshot:

```text
  60000 ms  critical component_failed       utility-a entered the modeled failed state.
 141000 ms  warning  ups_low_energy         ups-a reached its modeled low-energy threshold.
 168000 ms  critical ups_energy_depleted    ups-a exhausted its modeled usable battery energy.
 168000 ms  critical load_unserved          Modeled unserved load increased to 1000000 W.
```

To the millisecond. This is the acceptance-oracle property the whole engine is
built around: you can check any battery milestone with a calculator, and if the
engine disagrees, the engine is wrong.

### Runtime scales exactly inversely with load

Because the arithmetic is a single division, autonomy is exactly inversely
proportional to the discharge power. The bundled `reference-2n` UPS holds
120 kWh and carries 1.6 MW:

```text
432,000,000,000 mJ / 1,600,000 W = 270,000 ms
```

Half the load would be exactly 540,000 ms. There is no Peukert effect, no
capacity derating at high discharge rates, no temperature dependence, no
end-of-discharge voltage, no aging factor, and no state-of-health. A battery in
this model is a bucket of joules that empties at the rate you draw from it.

If your real question is "how long will this battery actually last", dc-twin
answers a strictly simpler question — "how long would an ideal bucket of *this
many* joules last at *this* draw" — and the difference between the two is
entirely on you to supply through the `usable_energy_mj` figure you author.

## Changing the battery, changing the outcome

Because the relationship is exact, sensitivity is easy to demonstrate. Take
`guide-n` and change only `usable_energy_mj` from 30 kWh to 45 kWh
(108,000,000,000 → 162,000,000,000 mJ):

```powershell
dc-twin compare results/n-30kwh.json results/n-45kwh.json
```

```json
{"metric_differences": {"interruption_duration_ms": {"left": 432000, "right": 378000}, "served_energy_mj": {"left": 168000000000, "right": 222000000000}, "service_ratio_ppm": {"left": 280000, "right": 370000}, "unserved_energy_mj": {"left": 432000000000, "right": 378000000000}}, "same_computation": false}
```

54 seconds more battery bought exactly 54 seconds less outage:
`162,000,000,000 / 1,000,000 = 162,000 ms` of autonomy instead of 108,000 ms,
so depletion moves from 168,000 ms to 222,000 ms. Nothing is compounded and
nothing is lost.

This is what dc-twin is genuinely good at: making the race between the battery
clock and the restoration clock explicit, and letting you sweep one input to
see exactly where the crossover lies.

## The low-energy threshold

The threshold raises a `warning`-severity `ups_low_energy` alarm once per UPS
per run and nothing else. It does not shed load, does not initiate a transfer,
does not change the allocation, and does not appear in any metric. It is a
marker on the timeline.

Choose it to mean something to you. A 20% threshold on a 270-second autonomy
gives you a marker 54 seconds before the lights go out; on a 30-minute
autonomy it gives you six minutes. The model does not know the difference and
will not tell you whether the warning arrives with useful time in hand.

## Multiple UPS units

Where several UPS units can each become battery sources, each is evaluated
independently: its own eligibility, its own stored energy, its own threshold,
its own depletion time. The engine takes the earliest pending milestone across
all of them as the next interval boundary.

The bundled `reference-n-plus-1` run shows the reserve case. UPS R2 fails at
120,000 ms and a simultaneous transfer closes reserve UPS R3's output. R3's
own 800 kW rating and R1's 800 kW rating force the split — the utility can
reach the load with only 800 kW through R1 — so R3 supplies the other 800 kW
from battery for exactly 30 seconds until its input feed closes:

```text
800,000 W * 30,000 ms = 24,000,000,000 mJ = 6.666667 kWh
```

The engine reports `"ups-r3": 24000000000` and zero for R1 and R2. Service is
never interrupted; the run's worst state is `battery_backed`, recorded solely
because of that 30-second bridge.

---

Previous: [5. Redundancy in this model's terms](05-redundancy.md) ·
Next: [7. Events, failures and maintenance windows](07-events.md)
