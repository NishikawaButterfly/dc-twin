# Simulation and Analysis Guide

This guide teaches an electrical engineer to model a topology in dc-twin, run a
scenario against it, and read the result correctly.

It is not an administrative manual and it is not a tutorial in data-center
electrical design. dc-twin is an engineering analysis tool, so this is an
engineering analysis guide. It assumes you know what a UPS, an ATS and a PDU
are, and it spends its effort on the part that is easy to get wrong: deciding
what a run actually proves.

Every number, alarm string, error message and hash quoted in this guide was
produced by running the software described here. Where a figure comes from a
hand calculation rather than an execution, the text says so.

## Chapters

| # | Chapter | What it covers |
|---:|---|---|
| 1 | [Introduction and who this is for](01-introduction.md) | Scope, audience, what the tool answers and refuses to answer |
| 2 | [Model concepts](02-model-concepts.md) | Components, connections, capacity, load, and what they deliberately do not mean |
| 3 | [Building a topology](03-building-a-topology.md) | Worked example, from a single feed to a redundant pair |
| 4 | [Loads and capacity](04-loads-and-capacity.md) | Demand, ratings, priority, and how a shortage is allocated |
| 5 | [Redundancy in this model's terms](05-redundancy.md) | What N, N+1 and 2N mean here, and what they do not |
| 6 | [UPS batteries and runtime](06-ups-and-runtime.md) | Eligibility, discharge, thresholds, depletion timing |
| 7 | [Events, failures and maintenance windows](07-events.md) | Event kinds, ordering, and the maintenance state |
| 8 | [Transfers](08-transfers.md) | Atomic transfers, the paralleling guard, and their limits |
| 9 | [Creating a scenario](09-creating-a-scenario.md) | Horizon, resolution, event authoring, validation |
| 10 | [Running a scenario](10-running-a-scenario.md) | The CLI, the API and the web explorer |
| 11 | [Reading the timeline](11-reading-the-timeline.md) | Segments, boundaries, flows, and the end-of-interval rule |
| 12 | [Reading alarms](12-reading-alarms.md) | The six alarm codes, and the runs that raise none |
| 13 | [Unserved energy](13-unserved-energy.md) | What the figure counts and what it does not |
| 14 | [Stranded capacity](14-stranded-capacity.md) | The isolation indicator, and its two causes |
| 15 | [Result hashes, determinism and replay](15-determinism-and-replay.md) | What the hash covers and how to verify it |
| 16 | [Comparing two scenarios](16-comparing-scenarios.md) | The three comparison routes and their gaps |
| 17 | [The reference scenarios](17-reference-scenarios.md) | What each bundled fixture demonstrates |
| 18 | [Degraded and maintenance states](18-degraded-states.md) | Interpreting the states between healthy and dark |
| 19 | [What conclusions may be drawn, and what may not](19-conclusions.md) | The chapter to read before quoting a run in a report |
| 20 | [Troubleshooting](20-troubleshooting.md) | Real rejection messages and what to do about them |
| 21 | [Glossary](21-glossary.md) | Terms as this model uses them |

## Related documents

This guide sits above the reference documentation and links to it rather than
repeating it. When you need the normative rule rather than the working
explanation, go to the source:

- [Model specification](../MODEL_SPECIFICATION.md) is normative. Where this
  guide and the specification disagree, the specification wins.
- [API reference](../API.md) documents every route, error family and contract.
- [Reference scenario](../REFERENCE_SCENARIO.md) and
  [reference topologies](../REFERENCE_TOPOLOGIES.md) carry the hand
  calculations that act as the acceptance oracle.
- [Architecture](../ARCHITECTURE.md) and the
  [decision records](../../adr/) explain how the engine is built.
- [Operations](../OPERATIONS.md) covers deployment, health and runbooks.
- [Threat model](../THREAT_MODEL.md) and
  [data provenance](../DATA_PROVENANCE.md) cover misuse and data policy.
- [Plain-language explainer](../EXPLAINER.md) is the starting point for readers
  without an electrical background.
