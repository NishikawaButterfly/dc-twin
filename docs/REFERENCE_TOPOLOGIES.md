# Reference Topologies: N and N+1

## Purpose and provenance

The bundled `reference-n` and `reference-n-plus-1` snapshots are fictional verification fixtures. Like the 2N fixture in [Reference Scenario](REFERENCE_SCENARIO.md), they were designed from first principles for this repository and contain no customer, site, tender, monitoring, or incident data. The hand calculations below are independent of the implementation and form an acceptance oracle.

All calculations assume lossless active power and constant demand. They are not electrical design calculations.

## The N topology (`reference-n`)

The N design has one nominal 1 MW path and no redundancy of any kind: a utility, transformer, switchgear, 1 MW UPS, and PDU feed a single 1 MW single-cord load. There is no standby generator and no alternate path. The UPS starts with 50 kWh of modeled usable energy:

```text
50 kWh * 3,600,000,000 mJ/kWh = 180,000,000,000 mJ
```

Every scenario on this snapshot has a 600,000 ms horizon and constant demand of 1,000,000 W:

```text
demanded_energy_mj
  = 1,000,000 W * 600,000 ms
  = 600,000,000,000 mJ

demanded_energy_kwh
  = 600,000,000,000 / 3,600,000,000
  = 166.666667 kWh
```

## Utility loss and restoration (`REF-DC-N-001`)

The scenario applies this sequence:

| Time | State change |
|---:|---|
| 0-120,000 ms | Normal operation: the utility serves 1 MW. |
| 120,000 ms | The utility fails; the UPS begins supplying the full 1 MW from battery. |
| 264,000 ms | The UPS reaches its 20% low-energy threshold; this is a derived alarm boundary. |
| 300,000 ms | The UPS reaches zero; the full 1 MW becomes unserved. |
| 420,000 ms | The utility is restored and service resumes through the same path. |

### Battery proof

The UPS starts discharging at `120,000 ms` with its full 180,000,000,000 mJ balance and supplies 1 MW. Its 20% threshold is:

```text
180,000,000,000 mJ * 20% = 36,000,000,000 mJ
```

The time required to move from the full balance to that threshold is:

```text
(180,000,000,000 - 36,000,000,000) mJ / 1,000,000 W
  = 144,000 ms

threshold time = 120,000 + 144,000 = 264,000 ms
```

The time to exhaust the full balance at 1 MW is:

```text
180,000,000,000 mJ / 1,000,000 W = 180,000 ms
depletion time = 120,000 + 180,000 = 300,000 ms
```

### Interruption and energy proof

The single interruption lasts from `300,000` to `420,000 ms`:

```text
interruption_duration_ms = 420,000 - 300,000 = 120,000 ms

unserved_energy_mj
  = 1,000,000 W * 120,000 ms
  = 120,000,000,000 mJ

unserved_energy_kwh
  = 120,000,000,000 / 3,600,000,000
  = 33.333333 kWh

served_energy_mj
  = 600,000,000,000 - 120,000,000,000
  = 480,000,000,000 mJ

served_energy_kwh
  = 480,000,000,000 / 3,600,000,000
  = 133.333333 kWh

service_ratio
  = 480,000,000,000 / 600,000,000,000
  = 0.8
  = 80%
  = 800,000 ppm exactly
```

### N acceptance values

| Expected metric or transition | Value |
|---|---:|
| Demanded energy | 600,000,000,000 mJ / 166.666667 kWh |
| Served energy | 480,000,000,000 mJ / 133.333333 kWh |
| Unserved energy | 120,000,000,000 mJ / 33.333333 kWh |
| Service ratio | 800,000 ppm / 80% |
| Interruption duration | 120,000 ms |
| Interruption count | 1 |
| Peak demand | 1,000,000 W |
| Peak served | 1,000,000 W |
| Peak stranded capacity | 0 W |
| Minimum served | 0 W |
| Worst modeled redundancy state | `no_path` |
| UPS N total discharge | 180,000,000,000 mJ / 50 kWh |
| UPS N low-energy transition | 264,000 ms |
| UPS N depletion transition | 300,000 ms |
| Service restoration | 420,000 ms |

During the outage, the failed utility and the depleted UPS contribute no available source capacity, so the normative stranded-capacity formula yields `min(1 MW unserved, 0 W unused available source) = 0 W`. Nothing is isolated from the load; there is simply nothing left to serve it.

## The N+1 topology (`reference-n-plus-1`)

The N+1 design has one nominal 2 MW utility path. Between an input and an output switchgear sit three 800 kW UPS units with 120 kWh of modeled usable energy each:

```text
120 kWh * 3,600,000,000 mJ/kWh = 432,000,000,000 mJ
```

Two fictional single-cord loads each demand 800 kW, so total demand is 1.6 MW and any two UPS units carry it. UPS R1 and UPS R2 normally carry 800 kW each. Reserve UPS R3 keeps both its input and output connections open; its output closes by static transfer when a running UPS fails, and its input feed is closed separately.

Every scenario on this snapshot has a 600,000 ms horizon and constant total demand of 1,600,000 W:

```text
demanded_energy_mj
  = 1,600,000 W * 600,000 ms
  = 960,000,000,000 mJ

demanded_energy_kwh
  = 960,000,000,000 / 3,600,000,000
  = 266.666667 kWh
```

## Absorbed UPS failure (`REF-DC-NP1-001`)

The scenario applies this sequence:

| Time | State change |
|---:|---|
| 0-120,000 ms | Normal operation: UPS R1 and UPS R2 carry 800 kW each from the utility. |
| 120,000 ms | UPS R2 fails; at the same instant an atomic transfer closes reserve UPS R3's output. R3 supplies 800 kW from battery while R1 continues to pass 800 kW of utility power. |
| 150,000 ms | An atomic transfer closes R3's input feed; the utility again carries the full 1.6 MW and the battery bridge ends. |

Service is never interrupted. The two events at `120,000 ms` are one atomic group, and the model evaluates service after the full group.

### Bridge energy proof

During the bridge, R3's own 800 kW rating and R1's 800 kW rating force the split: the utility can deliver at most 800 kW through R1, so R3 must supply the remaining 800 kW from battery. The bridge lasts from `120,000` to `150,000 ms`:

```text
bridge_duration_ms = 150,000 - 120,000 = 30,000 ms

ups_r3_discharge_mj
  = 800,000 W * 30,000 ms
  = 24,000,000,000 mJ

ups_r3_discharge_kwh
  = 24,000,000,000 / 3,600,000,000
  = 6.666667 kWh

remaining UPS R3 energy
  = 432,000,000,000 - 24,000,000,000
  = 408,000,000,000 mJ
  = 113.333333 kWh
```

The 20% low-energy threshold is `432,000,000,000 * 20% = 86,400,000,000 mJ`. The remaining 408,000,000,000 mJ stays far above it, so no low-energy alarm is expected. UPS R1 and the failed UPS R2 never discharge.

### Redundancy-state proof

Before the failure, the utility path can carry the full 1.6 MW through R1 and R2, so the modeled state is `single_path`. During the bridge, the utility path alone can reach only 800 kW (through R1) while R3 serves from battery, so the modeled state is `battery_backed`. After the input feed closes at `150,000 ms`, the utility path again carries the full demand through R1 and R3 and the state returns to `single_path`. The worst observed state, and therefore the scenario metric, is `battery_backed`.

### N+1 acceptance values

| Expected metric or transition | Value |
|---|---:|
| Demanded energy | 960,000,000,000 mJ / 266.666667 kWh |
| Served energy | 960,000,000,000 mJ / 266.666667 kWh |
| Unserved energy | 0 mJ / 0 kWh |
| Service ratio | 1,000,000 ppm / 100% |
| Interruption duration | 0 ms |
| Interruption count | 0 |
| Peak demand | 1,600,000 W |
| Peak served | 1,600,000 W |
| Minimum served | 1,600,000 W |
| Peak stranded capacity | 0 W |
| Worst modeled redundancy state | `battery_backed` |
| UPS R3 total discharge | 24,000,000,000 mJ / 6.666667 kWh |
| UPS R1 and R2 total discharge | 0 mJ |
| Battery bridge | 120,000 to 150,000 ms |

## Acceptance procedure

Automated tests should parse the published snapshots and scenarios, reproduce every exact integer metric above, assert the derived transition times, verify conservation identities for every timeline segment, and replay each result to the same computation hash. Presentation-layer decimal values may be rounded, but normative integers must match exactly.
