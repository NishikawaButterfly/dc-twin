# 8. Transfers

A transfer is the only way connection positions ever change. It deserves its
own chapter because it is the event kind most likely to be read as something it
is not.

## What an atomic transfer is

```json
{
  "id": "event-002-transfer-loads-to-a",
  "time_ms": 62000,
  "kind": "atomic_transfer",
  "open_connection_ids": ["pdu-b-to-load-1-normal", "pdu-b-to-load-2-normal"],
  "close_connection_ids": ["pdu-a-to-load-1-transfer", "pdu-a-to-load-2-transfer"]
}
```

Every listed connection changes position as one indivisible state transition.
All opens and all closes take effect together, and the capacity solver runs
once afterwards. There is no intermediate state in which some breakers have
moved and others have not, and no interval — however short — in which the load
is momentarily disconnected.

Two authoring rules are enforced:

- A transfer must open or close at least one connection.
- The same connection may not appear in both lists.

## What an atomic transfer is not

**It is not a command.** Nothing is instructed. The event asserts that, at this
millisecond, these connections are in these positions. The
[model specification](../MODEL_SPECIFICATION.md) states this deliberately: the
event describes a scenario state change; it is not a command to physical
equipment.

**It is not instantaneous in the real sense.** "Atomic" here means indivisible
in the model's event ordering. It does not model a break-before-make sequence,
a static-switch transfer time, a contactor operating time, an in-phase transfer
window, or a load's ride-through capability. If the real transfer takes 8
milliseconds and your loads cannot tolerate it, dc-twin has no way to express
that, and its report of uninterrupted service is not evidence about your loads.

**It is not a switching procedure.** The model has no interlocks, no
permissives, no sequence-of-operations validation and no operator. A transfer
that would be electrically catastrophic — closing onto a fault, back-feeding a
de-energised section, paralleling out-of-phase sources — will execute in the
model without comment, with the single exception below.

**It is not automatic.** No transfer ever fires by itself. An ATS in this model
does not transfer on loss of source. It is a node with a rating and one
constraint. If you want the ATS to transfer, you write the transfer event.

## The one guard: source paralleling at ATS and STS

The engine refuses to let more than one input connection be closed at an ATS or
STS node. It checks this twice: on the initial snapshot state, and after every
runtime transfer.

The snapshot check:

```text
topology.parallel_sources: ats-a has more than one initially closed input; v1 forbids paralleling.
```

The runtime check is the one to know about. Take the bundled `reference-2n`
topology, fail utility A, declare generator A running after its 15-second start
delay, and then close the generator input **without opening the utility
input**:

```json
{ "id": "event-003-close-generator-input", "time_ms": 90000,
  "kind": "atomic_transfer", "open_connection_ids": [],
  "close_connection_ids": ["generator-a-to-ats-a"] }
```

Validation passes:

```powershell
dc-twin validate-scenario examples/synthetic/reference-2n.snapshot.json parallel.scenario.json
```

```json
{"hash": "784d78756746c14eeac272a19fff9b002cbe2d7fb92256d6fe6e8d65593c9dd2", "scenario_id": "GUIDE-PARALLEL", "valid": true}
```

The run does not:

```powershell
dc-twin run examples/synthetic/reference-2n.snapshot.json parallel.scenario.json --output results/parallel.json
```

```json
{"detail": "Runtime transfer would parallel inputs at ats-a: utility-a-to-ats-a, generator-a-to-ats-a.", "error_code": "topology.parallel_sources"}
```

Exit code 2, no result file written.

Two things to take from this. First, **`validate-scenario` passing does not
mean the scenario will run.** Structural validation cannot see state that only
exists mid-simulation. Budget for the possibility that a scenario fails at
`run` time after validating cleanly.

Second, and more important: **this guard is a contract check, not a safety
analysis.** It enforces one modelling rule — v1 does not model source
paralleling, so the graph must never present two closed sources at a transfer
switch. It is not asserting anything about synchronisation, phase angle, closed
transition capability, or whether a real bus-tie closure would be safe. The
same closure at a `switchgear` node instead of an `ats` node would execute
without complaint, because the guard only inspects ATS and STS kinds.

## The correct pattern

Open and close together, in the same event:

```json
{ "id": "event-005-transfer-a-to-generator", "time_ms": 135000,
  "kind": "atomic_transfer",
  "open_connection_ids": ["utility-a-to-ats-a"],
  "close_connection_ids": ["generator-a-to-ats-a"] }
```

That is how the bundled `REF-DC-2N-GEN-SUCCESS` scenario transfers to the
generator, and the result is 100% service with a 15-second battery bridge of
exactly 24,000,000,000 mJ.

## Transfers and the redundancy calculation

Recall from chapter 5 that redundancy evidence hypothetically closes eligible
*load-input* connections on the path being tested. This has a specific
consequence for how you model transfer cords.

In `reference-2n`, each load has four incoming edges: `normal` and `transfer`
from each of PDU A and PDU B, each rated 400 kW. During the composite scenario
the loads are moved to path A by opening both B-normal edges and closing both
A-transfer edges. Path A then supplies 800 kW to each load through two 400 kW
edges.

When the redundancy calculation asks "could path B carry everything alone", it
hypothetically closes path B's load-input edges — but only if both endpoints
are available. While `pdu-b` is in maintenance it is not available, so nothing
is closed and path B does not qualify. The moment maintenance ends at
420,000 ms, `pdu-b` becomes available again and the hypothetical closure
becomes possible, which is why the state can improve before any real transfer
event fires.

The practical rule: model alternate cords as explicit connections with real
ratings, and let the ratings do the work. If a transfer cord is rated below the
load it must pick up, the redundancy evidence will correctly refuse to count
that path — which is exactly the answer you want, and one you will not get from
a drawing.

## What you cannot model

- **Partial or staged transfers.** A connection is open or closed. There is no
  soft transfer, no ramp, no load sharing during changeover.
- **Transfer failure.** There is no way to say "the transfer was attempted and
  did not complete". You can model the outcome by simply not writing the close
  event, but the model will not distinguish that from a transfer nobody
  attempted.
- **Transfer time.** All transfers take zero milliseconds. If changeover time
  matters to your analysis, you must approximate it by placing the open and the
  close in two separate events at different timestamps — and then the model
  will report the gap as a genuine loss of supply, which may or may not be what
  you meant.
- **Retransfer logic.** No hysteresis, no return delay, no fail-to-retransfer.

---

Previous: [7. Events, failures and maintenance windows](07-events.md) ·
Next: [9. Creating a scenario](09-creating-a-scenario.md)
