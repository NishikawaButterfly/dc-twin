# Roadmap

The roadmap is ordered by evidence and risk reduction. It is directional, not a delivery commitment.

## 0.1 - Deterministic reference release

- Strict `ElectricalDesignSnapshot`, scenario, and result contracts.
- Deterministic active-power capacity allocation and replay.
- UPS energy depletion, event transitions, alarms, synthetic telemetry, and traceable metrics.
- Synthetic N, N+1, and 2N modeling primitives with an independently calculated 2N reference case.
- Versioned API, PostgreSQL persistence, interactive explorer, Docker workflow, and CI quality gates.

## 0.2 - Validation and observability

- Property-based invariants for energy conservation and event ordering.
- OpenTelemetry traces and structured operational metrics.
- Explicit retention controls and administrative deletion workflow.
- Larger synthetic topology and performance corpus.
- Signed build provenance and software bill of materials.

## 0.3 - Scenario analysis

- Side-by-side run comparison and difference explanations.
- Monte Carlo orchestration around the deterministic kernel, with seeded reproducibility.
- Maintenance-window templates and sensitivity sweeps.
- Additional synthetic N and N+1 independently calculated reference cases.

## Deliberately out of scope

The roadmap does not include AC or DC circuit solution, voltage drop, reactive power, harmonics, transient stability, short-circuit duty, protection coordination, arc-flash analysis, equipment certification, regulatory compliance, live SCADA/BMS connectivity, or autonomous control. Those functions require purpose-built engineering tools, governed data, qualified review, and separate safety cases.
