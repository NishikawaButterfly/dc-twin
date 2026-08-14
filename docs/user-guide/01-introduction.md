# 1. Introduction and who this is for

## What dc-twin answers

dc-twin answers one question, repeatedly and exactly:

> Given a directed topology with stated capacities, a set of loads with stated
> demand, finite UPS energy, and a timed sequence of state changes, how much
> demand is served during each interval, by which path, and when does that
> change?

Everything else in the tool exists to make that answer traceable: the timeline
records which path carried the power, the alarms record why the state changed,
the metrics integrate the intervals into energy figures, and the hashes let a
reviewer reproduce the whole thing.

The question is narrower than it sounds. dc-twin is a capacity and connectivity
bookkeeper. It moves integer watts along a graph of integer ratings and debits
integer millijoules from batteries. It does not solve any electrical equation.

## Who this guide is for

You should read this guide if you are an electrical or critical-facilities
engineer who wants to reason about event ordering and capacity consequences in
a redundant power topology, and who intends to quote the result somewhere that
matters.

That last clause is the important one. A run is easy to produce and easy to
misread. Chapter 19 exists because the difference between a sound and an
unsound conclusion drawn from the *same* run is often a single word in a
sentence. If you read only one chapter before putting a dc-twin figure into a
report, read that one.

If none of the vocabulary here is familiar, start with the
[plain-language explainer](../EXPLAINER.md) instead.

## What dc-twin is not

The README and the [model specification](../MODEL_SPECIFICATION.md) both carry
scope disclaimers. This guide states them again, and more sharply, because a
manual is the document an engineer quotes.

**It is not a short-circuit or fault study.** There is no impedance, no fault
current, no interrupting duty. A connection in this model has one property that
matters, an integer watt rating, and it either carries flow or it does not.

**It is not protection coordination.** No relay, breaker curve, fuse or
selectivity scheme is modeled. When this guide says a component "failed", it
means a scenario author declared it unavailable at a timestamp. Nothing
detected anything, nothing tripped, and no device decided anything.

**It is not a Tier assessment.** The model reports states named `two_n`,
`single_path` and so on. Those are labels for what the graph could do at one
instant under one deliberate calculation, described in chapter 5. They are not
Uptime Institute classifications, they do not consider continuous cooling,
compartmentalisation, concurrent maintainability as a certification body
defines it, or anything outside the electrical graph you supplied.

**It is not a live twin.** Nothing in this repository connects to equipment.
There is no Modbus, no BACnet, no SCADA, no historian. The telemetry stream the
engine emits is derived arithmetically from the simulation and every point is
stamped `quality=synthetic`. It has never touched a sensor.

**It is not a design tool.** No output implies code compliance, construction
suitability, equipment selection, or that a switching sequence is safe to
perform.

**It is not probabilistic.** There is no failure rate, no MTBF, no Monte Carlo,
no availability calculation. You tell it what fails and when. It tells you the
consequence of exactly that. A service ratio of 94.7% means "in this invented
ten minutes, 94.7% of the demanded energy was served". It does not mean a
facility is available 94.7% of the time, and the distance between those two
sentences is the distance between analysis and malpractice.

## The one rule that governs every result

**A dc-twin result is only as good as the capacities and the reliability
assumptions you fed it.**

The engine is exact. Its arithmetic is integer, its ordering is deterministic,
and it will reproduce a result byte for byte on another machine. None of that
says anything about whether the ratings in your snapshot match the equipment,
whether the demand figure matches the real load, whether the UPS really holds
the energy you claimed, or whether the failure you injected is the one that
would actually happen.

Exactness is not accuracy. dc-twin gives you the first and cannot give you the
second. Everything in chapter 19 follows from that sentence.

## Conventions in this guide

- Commands are shown for PowerShell on Windows, which is where the outputs in
  this guide were produced. They work unchanged in a POSIX shell apart from
  path separators.
- All quoted output is real. It was produced by running the command shown
  against the engine version stated in the surrounding text.
- Normative quantities are integers: watts (`W`), millijoules (`mJ`),
  milliseconds (`ms`) and parts per million (`ppm`). Kilowatt-hour figures are
  presentation conversions at `1 kWh = 3,600,000,000 mJ` and are always
  rounded views of an exact integer.
- Where a figure is derived by hand rather than executed, the text says
  "by hand" or shows the arithmetic.

## Version this guide describes

The runs in this guide were produced against engine version `1.0.0`, reported
by the CLI, the API `/health/live` route and every result envelope. Verify
yours before comparing hashes:

```powershell
dc-twin run examples/synthetic/reference-2n.snapshot.json `
  examples/synthetic/scenarios/healthy.scenario.json --output results/healthy.json
```

```json
{"computation_hash": "1f1e00ac43d257059830ab0ebb1e05c60941edb68ae1111f62cc23484775f7b8", "output": "...\\results\\healthy.json", "run_id": "run-1f1e00ac43d25705"}
```

If your hash for `REF-DC-2N-HEALTHY` differs from
`1f1e00ac43d257059830ab0ebb1e05c60941edb68ae1111f62cc23484775f7b8`, you are on
a different engine version and the specific numbers in this guide will not
match yours. The reasoning still will.

---

Next: [2. Model concepts](02-model-concepts.md)
