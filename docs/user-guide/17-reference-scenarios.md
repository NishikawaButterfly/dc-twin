# 17. The reference scenarios

The repository ships three synthetic topologies and five scenarios. They are
the fastest way to see the engine behave, they are the only thing the API and
the web explorer will run, and each was built to demonstrate one specific
thing.

Every figure in this chapter came from running
`python scripts/check_reference_results.py` and the CLI against the bundled
fixtures at engine version `1.0.0`. The hand calculations behind them are in
[REFERENCE_SCENARIO.md](../REFERENCE_SCENARIO.md) and
[REFERENCE_TOPOLOGIES.md](../REFERENCE_TOPOLOGIES.md), written independently of
the implementation as an acceptance oracle.

## The three topologies

| Snapshot | Shape | Loads | UPS energy |
|---|---|---|---|
| `reference-n` | one 1 MW path: utility, transformer, switchgear, UPS, PDU. No generator, no alternate | one 1 MW single-cord | 50 kWh (180,000,000,000 mJ) |
| `reference-n-plus-1` | one 2 MW utility, three 800 kW UPS units between an input and output switchgear, reserve unit normally open both sides | two 800 kW single-cord | 120 kWh each (432,000,000,000 mJ) |
| `reference-2n` | two 2 MW paths A and B, each with utility, standby generator, ATS, transformer, switchgear, UPS, PDU | two 800 kW dual-cord, four cords each at 400 kW | 120 kWh each (432,000,000,000 mJ) |

All three declare `data_classification: "synthetic"` and carry provenance
stating they were purpose-built for software verification from no operational,
customer or site data.

## The results, as the engine produced them

| Scenario | Snapshot | Demanded (mJ) | Served (mJ) | Unserved (mJ) | Ratio (ppm) | Interruption | Count | Peak stranded (W) | Worst state | UPS discharge (mJ) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| `REF-DC-2N-HEALTHY` | `reference-2n` | 960,000,000,000 | 960,000,000,000 | 0 | 1,000,000 | 0 ms | 0 | 0 | `two_n` | none |
| `REF-DC-2N-GEN-SUCCESS` | `reference-2n` | 960,000,000,000 | 960,000,000,000 | 0 | 1,000,000 | 0 ms | 0 | 0 | `battery_backed` | `ups-a` 24,000,000,000 |
| `REF-DC-2N-001` | `reference-2n` | 960,000,000,000 | 908,800,000,000 | 51,200,000,000 | 946,667 | 32,000 ms | 1 | 1,600,000 | `no_path` | `ups-a` 432,000,000,000 |
| `REF-DC-N-001` | `reference-n` | 600,000,000,000 | 480,000,000,000 | 120,000,000,000 | 800,000 | 120,000 ms | 1 | 0 | `no_path` | `ups-n` 180,000,000,000 |
| `REF-DC-NP1-001` | `reference-n-plus-1` | 960,000,000,000 | 960,000,000,000 | 0 | 1,000,000 | 0 ms | 0 | 0 | `battery_backed` | `ups-r3` 24,000,000,000 |

And the computation hashes, which are the thing to check first if your numbers
disagree with this table:

| Scenario | `computation_hash` |
|---|---|
| `REF-DC-2N-HEALTHY` | `1f1e00ac43d257059830ab0ebb1e05c60941edb68ae1111f62cc23484775f7b8` |
| `REF-DC-2N-GEN-SUCCESS` | `7c384ec1d8819490194ed8f6a34911bf142f0c61fc6f98c23a06a724bca6c666` |
| `REF-DC-2N-001` | `71c0ef262cfc15d0fd449b53adcbad62c8c51418ab33d211f64031e01c77b5a0` |
| `REF-DC-N-001` | `ccc58e6ac828e6e06d961eaa7f30455ee2977442a52c0da57b7e6ccfbed7bffb` |
| `REF-DC-NP1-001` | `c7be0bbf239dc8b1a99f8a911de55e1a127767233edaea2cb51fd9056858b78f` |

Every scenario has a 600,000 ms horizon and 1,000 ms resolution.

## What each one demonstrates

### `REF-DC-2N-HEALTHY` — the baseline

Zero events. Both utilities carry 800 kW each for ten minutes and neither UPS
discharges.

Demonstrates: the `two_n` state, and that stranded capacity is zero when
demand is fully served regardless of how much headroom exists. Two 2 MW paths
carry 1.6 MW and the metric reports `0`, because the metric is defined only in
the presence of unserved demand.

Use it as: the control run. If you are unsure whether an effect you see comes
from the topology or the scenario, run this first.

### `REF-DC-2N-GEN-SUCCESS` — the generator that works

PDU B enters maintenance at 62,000 ms and both loads transfer to path A.
Utility A fails at 120,000 ms and UPS A carries the full 1.6 MW until generator
A reaches its running state at 135,000 ms and the ATS transfers.

The 15,000 ms gap is exactly generator A's declared `start_delay_ms`. The
battery debit is exactly:

```text
1,600,000 W × 15,000 ms = 24,000,000,000 mJ = 6.666667 kWh
```

leaving 408,000,000,000 mJ, comfortably above the 20% threshold of
86,400,000,000 mJ, so no low-energy alarm fires.

```text
      0 ms  two_n           served= 1600000 unserved=       0 stranded=       0
  62000 ms  single_path     served= 1600000 unserved=       0 stranded=       0
 120000 ms  battery_backed  served= 1600000 unserved=       0 stranded=       0
 135000 ms  single_path     served= 1600000 unserved=       0 stranded=       0
```

Demonstrates: a clean generator transfer, the atomic open-and-close pattern
from chapter 8, and the `battery_backed` state recorded for a 15-second bridge
in a run that never lost a watt. The worst state is `battery_backed` and the
service ratio is 100% — a useful reminder that the worst-state metric is a
floor, not a verdict.

### `REF-DC-2N-001` — the composite failure

The headline fixture, and the one behind the README screenshot.

| Time | State change |
|---:|---|
| 62,000 ms | PDU B enters maintenance; an atomic transfer moves both loads to path A |
| 120,000 ms | Utility A fails; UPS A begins supplying the full 1.6 MW |
| 135,000 ms | Generator A reaches its 15-second boundary and is declared failed |
| 336,000 ms | UPS A crosses its 20% low-energy threshold |
| 390,000 ms | UPS A reaches zero; all 1.6 MW becomes unserved |
| 420,000 ms | PDU B maintenance ends, but the B load connections are still open |
| 422,000 ms | An atomic transfer to path B restores service |

```text
      0 ms  two_n           served= 1600000 unserved=       0 stranded=       0
  62000 ms  single_path     served= 1600000 unserved=       0 stranded=       0
 120000 ms  battery_backed  served= 1600000 unserved=       0 stranded=       0
 390000 ms  no_path         served=       0 unserved= 1600000 stranded= 1600000
 422000 ms  single_path     served= 1600000 unserved=       0 stranded=       0
```

The battery arithmetic, checkable by hand:

```text
threshold_mj    = 432,000,000,000 × 20% = 86,400,000,000 mJ
low_energy_time = 120,000 + (432e9 - 86.4e9) / 1,600,000 = 336,000 ms
depletion_time  = 120,000 + 432e9 / 1,600,000 = 390,000 ms
interruption    = 422,000 - 390,000 = 32,000 ms
unserved        = 1,600,000 W × 32,000 ms = 51,200,000,000 mJ
```

Demonstrates: nearly everything. Maintenance overlapping a failure, a generator
start failure, the full battery milestone sequence, stranded capacity from
isolation, and the two-second gap between `maintenance_end` at 420,000 ms and
the transfer at 422,000 ms — proof that restoring a component does not restore
service when the connections to it were opened.

It is also the best example of the "worst state" rule. The run reports
`no_path` for a 32-second window inside a ten-minute scenario that was
otherwise fully served, and `no_path` is what the run-level metric says.

### `REF-DC-N-001` — no redundancy at all

Utility N fails at 120,000 ms; the UPS carries 1 MW to depletion; utility N is
restored at 420,000 ms.

```text
low_energy_time = 120,000 + (180e9 - 36e9) / 1,000,000 = 264,000 ms
depletion_time  = 120,000 + 180e9 / 1,000,000 = 300,000 ms
interruption    = 420,000 - 300,000 = 120,000 ms
service ratio   = 480e9 / 600e9 = 800,000 ppm exactly
```

```text
      0 ms  single_path     served= 1000000 unserved=       0 stranded=       0
 120000 ms  battery_backed  served= 1000000 unserved=       0 stranded=       0
 300000 ms  no_path         served=       0 unserved= 1000000 stranded=       0
 420000 ms  single_path     served= 1000000 unserved=       0 stranded=       0
```

Demonstrates: the battery-clock-versus-restoration-clock race in its purest
form, and — importantly — **stranded capacity of zero during a total outage**.
During the interruption the failed utility contributes no available source
capacity and the depleted UPS has no energy, so
`min(1,000,000 unserved, 0 unused) = 0`. Nothing is isolated. There is simply
nothing left to serve the load. Compare it against `REF-DC-2N-001`, where the
same `no_path` state carries 1.6 MW of stranded capacity because utility B was
alive the whole time and could not reach the loads.

Those two runs, read together, are the clearest available demonstration of what
the stranded-capacity metric actually distinguishes.

### `REF-DC-NP1-001` — reserve absorbs a failure

UPS R2 fails at 120,000 ms and, in the same atomic group, reserve UPS R3's
output closes. R3 supplies 800 kW from battery while R1 passes 800 kW of
utility power, because both are rated 800 kW and neither can do more. At
150,000 ms a second transfer closes R3's input feed and the bridge ends.

```text
bridge         = 150,000 - 120,000 = 30,000 ms
r3 discharge   = 800,000 W × 30,000 ms = 24,000,000,000 mJ = 6.666667 kWh
r3 remaining   = 432e9 - 24e9 = 408,000,000,000 mJ
```

```text
      0 ms  single_path     served= 1600000 unserved=       0 stranded=       0
 120000 ms  battery_backed  served= 1600000 unserved=       0 stranded=       0
 150000 ms  single_path     served= 1600000 unserved=       0 stranded=       0
```

R1 and R2 never discharge. Service is never interrupted.

Demonstrates: equal-time event grouping — the failure and the reserve pickup
land together and service is evaluated once, after both, so no artificial
zero-duration outage is recorded. Also demonstrates that N+1 has no state name:
the run reports `single_path` either side of the bridge and `battery_backed`
during it, and the redundancy is evidenced by the *absence* of unserved energy
across a component failure.

Note also that every component in this topology is tagged `path: "A"`, so this
snapshot can never report `two_n` under any circumstances. That is correct for
what it models and worth knowing before you read anything into the state names.

## Verifying them yourself

The repository ships an independent check that parses the published fixtures,
reproduces every metric, and compares against expected values committed
separately from the engine in
`examples/synthetic/expected/reference-metrics.json`:

```powershell
python scripts/check_contracts.py
python scripts/check_reference_results.py
```

```text
Validated 3 contracts, 3 reference snapshots, and 5 reference scenarios.
```

followed by the full metric dump for all five scenarios. If that command
disagrees with the table above, you are on a different engine version.

## Using them as templates

The five scenarios are the best starting point for your own work, in this
order:

1. Copy `healthy.scenario.json` — eleven lines, zero events — and point it at
   your own snapshot. Run it. A healthy run tells you whether your topology is
   connected and rated the way you think, before any failure confuses the
   picture. Chapter 14's trap topology was found exactly this way.
2. Copy `n-utility-loss.scenario.json` for a single failure with restoration.
3. Copy `generator-success.scenario.json` for the correct atomic open-and-close
   transfer pattern, which is the easiest thing to get wrong.
4. Copy `composite-failure.scenario.json` when you want the full shape of a
   multi-event narrative.

Remember that a scenario is bound to its snapshot by `snapshot_id`, so the
first edit is always that field.

---

Previous: [16. Comparing two scenarios](16-comparing-scenarios.md) ·
Next: [18. Degraded and maintenance states](18-degraded-states.md)
