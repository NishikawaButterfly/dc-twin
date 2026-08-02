# Reference Scenario

## Purpose and provenance

The bundled `reference-2n` snapshot is a fictional verification fixture. It was designed from first principles for this repository and contains no customer, site, tender, monitoring, or incident data. The hand calculations below are independent of the implementation and form an acceptance oracle. The bundled N and N+1 fixtures are documented the same way in [Reference Topologies](REFERENCE_TOPOLOGIES.md).

The topology has two nominal 2 MW paths, A and B. Each path contains a utility, standby generator, ATS, transformer, switchgear, 2 MW UPS, and PDU. Each UPS starts with 120 kWh of modeled usable energy:

```text
120 kWh * 3,600,000,000 mJ/kWh = 432,000,000,000 mJ
```

Two fictional dual-cord loads each demand 800 kW. Normally, each path supplies 400 kW to each load, so path A carries 800 kW and path B carries 800 kW. Supplemental 400 kW connections are normally open and are closed by an explicit transfer event when one path must carry both loads.

All calculations assume lossless active power and constant demand. They are not electrical design calculations.

## Common demand calculation

Every scenario has a 600,000 ms horizon and constant total demand of 1,600,000 W:

```text
demanded_energy_mj
  = 1,600,000 W * 600,000 ms
  = 960,000,000,000 mJ

demanded_energy_kwh
  = 960,000,000,000 / 3,600,000,000
  = 266.666667 kWh
```

## Healthy operation (`REF-DC-2N-HEALTHY`)

Both utilities remain available and the normal connections remain closed. Each utility path serves 800 kW for the full horizon. Neither UPS discharges.

| Expected metric | Value |
|---|---:|
| Demanded energy | 960,000,000,000 mJ / 266.666667 kWh |
| Served energy | 960,000,000,000 mJ / 266.666667 kWh |
| Unserved energy | 0 mJ / 0 kWh |
| Service ratio | 1,000,000 ppm / 100% |
| Interruption duration | 0 ms |
| Interruption count | 0 |
| UPS A minimum energy | 432,000,000,000 mJ / 120 kWh |
| UPS B minimum energy | 432,000,000,000 mJ / 120 kWh |

Stranded capacity is zero because the metric is defined only in the presence of unserved demand; it is not spare margin.

## Planned path maintenance and successful generator transfer (`REF-DC-2N-GEN-SUCCESS`)

The scenario narrative initiates a planned transfer away from path B at `60,000 ms`; initiation has no separate state event. At `62,000 ms`, PDU B enters maintenance and an atomic connection event moves both 800 kW loads to path A. Utility A then carries the full 1.6 MW.

At `120,000 ms`, utility A fails. UPS A carries the full 1.6 MW until generator A reaches its declared running state and the ATS input transfer completes at `135,000 ms`. The 15,000 ms interval equals generator A's declared modeled start delay.

UPS A energy debit before transfer is:

```text
1,600,000 W * 15,000 ms = 24,000,000,000 mJ
24,000,000,000 mJ / 3,600,000,000 = 6.666667 kWh

remaining UPS A energy
  = 432,000,000,000 - 24,000,000,000
  = 408,000,000,000 mJ
  = 113.333333 kWh
```

There is no modeled interruption, so demanded and served energy both remain 960,000,000,000 mJ, the service ratio is 1,000,000 ppm, and interruption duration and count remain zero.

## Composite failure and recovery (`REF-DC-2N-001`)

The composite scenario applies this sequence:

| Time | State change |
|---:|---|
| 0-60,000 ms | Normal split operation: path A serves 800 kW and path B serves 800 kW. |
| 60,000 ms | The scenario narrative initiates a planned transfer away from path B; there is no separate model-state event. |
| 62,000 ms | PDU B enters maintenance and an atomic connection event moves both loads to path A. |
| 120,000 ms | Utility A fails; UPS A begins supplying the full 1.6 MW. |
| 135,000 ms | Generator A reaches its 15-second start boundary but is declared failed. |
| 336,000 ms | UPS A reaches its 20% low-energy threshold; this is a derived alarm boundary. |
| 390,000 ms | UPS A reaches zero; all 1.6 MW becomes unserved. |
| 420,000 ms | PDU B maintenance ends, but its load connections remain open. |
| 422,000 ms | An atomic load-edge transfer to the available path B restores service. |

### Battery proof

UPS A starts discharging at `120,000 ms` with its full 432,000,000,000 mJ balance and supplies 1.6 MW. Its 20% threshold is:

```text
432,000,000,000 mJ * 20% = 86,400,000,000 mJ
```

The time required to move from the full balance to that threshold is:

```text
(432,000,000,000 - 86,400,000,000) mJ / 1,600,000 W
  = 216,000 ms

threshold time = 120,000 + 216,000 = 336,000 ms
```

The time to exhaust the full balance at 1.6 MW is:

```text
432,000,000,000 mJ / 1,600,000 W = 270,000 ms
depletion time = 120,000 + 270,000 = 390,000 ms
```

### Interruption and energy proof

The single interruption lasts from `390,000` to `422,000 ms`:

```text
interruption_duration_ms = 422,000 - 390,000 = 32,000 ms

unserved_energy_mj
  = 1,600,000 W * 32,000 ms
  = 51,200,000,000 mJ

unserved_energy_kwh
  = 51,200,000,000 / 3,600,000,000
  = 14.222222 kWh

served_energy_mj
  = 960,000,000,000 - 51,200,000,000
  = 908,800,000,000 mJ

served_energy_kwh
  = 908,800,000,000 / 3,600,000,000
  = 252.444444 kWh

service_ratio
  = 908,800,000,000 / 960,000,000,000
  = 0.9466666667
  = 94.6667%
  = 946,667 ppm when rounded to the nearest ppm
```

### Composite acceptance values

| Expected metric or transition | Value |
|---|---:|
| Demanded energy | 960,000,000,000 mJ / 266.666667 kWh |
| Served energy | 908,800,000,000 mJ / 252.444444 kWh |
| Unserved energy | 51,200,000,000 mJ / 14.222222 kWh |
| Service ratio | 946,667 ppm / 94.6667% |
| Interruption duration | 32,000 ms |
| Interruption count | 1 |
| Peak demand | 1,600,000 W |
| Peak served | 1,600,000 W |
| Peak stranded capacity | 1,600,000 W |
| Minimum served | 0 W |
| Worst modeled redundancy state | `no_path` |
| UPS A low-energy transition | 336,000 ms |
| UPS A depletion transition | 390,000 ms |
| Service restoration | 422,000 ms |

During the outage, generator A remains unavailable and its rating is therefore not *available source capacity*. Utility B has 2 MW of available source capacity, but it cannot reach the loads while PDU B is in maintenance and then while the B load edges remain open. The normative stranded-capacity formula therefore yields `min(1.6 MW unserved, 2 MW unused available source) = 1.6 MW`. This is an isolation indicator, not a switching recommendation.

## Acceptance procedure

Automated tests should parse the published snapshot and scenarios, reproduce every exact integer metric above, assert the derived transition times, verify conservation identities for every timeline segment, and replay each result to the same computation hash. Presentation-layer decimal values may be rounded, but normative integers must match exactly.
