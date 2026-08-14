# 3. Building a topology

This chapter builds one topology twice: first as a single feed, then as a
redundant pair. The two snapshots differ only by the addition of a second path,
and in chapter 5 the same failure is injected into both to show what the
redundancy buys.

The snapshots here are complete and runnable. Copy them into files, validate
them, and keep them: chapters 5, 7, 11, 12, 14 and 15 all run against them.

## The document envelope

Every snapshot starts with the same eleven top-level fields, all required, none
optional, and no others accepted:

```json
{
  "schema_id": "dc-twin.electrical-design-snapshot",
  "schema_version": "1.0.0",
  "snapshot_id": "guide-n",
  "design_revision": "1.0.0",
  "data_classification": "synthetic",
  "provenance": { "title": "...", "created_by": "...", "method": "..." },
  "units": { "power": "W", "energy": "mJ", "time": "ms" },
  "assumptions": [ "..." ],
  "components": [ ... ],
  "connections": [ ... ],
  "redundancy_groups": [ ... ]
}
```

Four of these are effectively constants. `schema_id` and `schema_version` must
be exactly the values above. `units` must be exactly `W`, `mJ` and `ms`.
`data_classification` must be the string `synthetic`, and the parser refuses
anything else:

```json
{"detail": "Invalid value at $.data_classification: public fixtures must be classified synthetic", "error_code": "contract.invalid_field"}
```

That is a deliberate policy gate, not a modelling choice. See
[DATA_PROVENANCE.md](../DATA_PROVENANCE.md). It means you cannot use this tool
on real site data without deliberately mislabelling that data, which is exactly
the friction it was designed to create.

`provenance` and `assumptions` are free text and are not interpreted by the
engine at all. They are, however, hashed into the snapshot hash, so changing an
assumption string changes every downstream result hash. Write them as though a
reviewer will read them, because that is their only function.

The parser rejects any field it does not recognise, at any depth:

```powershell
dc-twin validate-design bad/extra-field.snapshot.json
```

```json
{"detail": "Invalid value at $.components[0]: unexpected fields: voltage_v", "error_code": "contract.invalid_field", "invalid_params": [{"name": "$.components[0]", "reason": "unexpected fields: voltage_v"}]}
```

There is nowhere to record a voltage, a cable size, an asset tag or a
manufacturer. If you need that information alongside the model, it lives
outside the snapshot.

## Stage one: a single feed

One utility, one switchgear, one UPS, one PDU, one load. Ratings 1.2 MW through
the chain, a 1 MW load, and 30 kWh of usable UPS energy
(`30 * 3,600,000,000 = 108,000,000,000 mJ`).

```json
{
  "schema_id": "dc-twin.electrical-design-snapshot",
  "schema_version": "1.0.0",
  "snapshot_id": "guide-n",
  "design_revision": "1.0.0",
  "data_classification": "synthetic",
  "provenance": {
    "title": "Guide worked example: single feed",
    "created_by": "NishikawaButterfly",
    "method": "Fictional topology written for the analysis guide; no operational, customer, or site data was used."
  },
  "units": { "power": "W", "energy": "mJ", "time": "ms" },
  "assumptions": [
    "The model allocates lossless active-power capacity only.",
    "One 1.2 MW feed supplies one 1 MW single-cord load.",
    "The UPS holds 30 kWh of modeled usable energy and does not recharge."
  ],
  "components": [
    { "id": "utility-a", "label": "Synthetic utility A", "kind": "utility",
      "path": "A", "capacity_w": 1200000, "initial_status": "available" },
    { "id": "switchgear-a", "label": "Synthetic switchgear A", "kind": "switchgear",
      "path": "A", "capacity_w": 1200000, "initial_status": "available" },
    { "id": "ups-a", "label": "Synthetic UPS A", "kind": "ups",
      "path": "A", "capacity_w": 1200000, "initial_status": "available",
      "usable_energy_mj": 108000000000, "low_energy_threshold_pct": 25 },
    { "id": "pdu-a", "label": "Synthetic PDU A", "kind": "pdu",
      "path": "A", "capacity_w": 1200000, "initial_status": "available" },
    { "id": "it-load-1", "label": "Synthetic IT load 1", "kind": "load",
      "path": "shared", "capacity_w": 1000000, "initial_status": "available",
      "demand_w": 1000000, "priority": 1, "service_order": 1 }
  ],
  "connections": [
    { "id": "utility-a-to-switchgear-a", "from_component": "utility-a",
      "to_component": "switchgear-a", "capacity_w": 1200000, "initial_closed": true },
    { "id": "switchgear-a-to-ups-a", "from_component": "switchgear-a",
      "to_component": "ups-a", "capacity_w": 1200000, "initial_closed": true },
    { "id": "ups-a-to-pdu-a", "from_component": "ups-a",
      "to_component": "pdu-a", "capacity_w": 1200000, "initial_closed": true },
    { "id": "pdu-a-to-load-1", "from_component": "pdu-a",
      "to_component": "it-load-1", "capacity_w": 1000000, "initial_closed": true }
  ],
  "redundancy_groups": [
    { "id": "source-n", "mode": "N", "members": ["utility-a"] }
  ]
}
```

Validate it:

```powershell
dc-twin validate-design guide-n.snapshot.json
```

```json
{"hash": "544d1cb1936a52bd2dfab2d477ad07141cfc625949b03ad3cda53940efde9f8b", "snapshot_id": "guide-n", "valid": true}
```

The returned `hash` is the SHA-256 of the canonical JSON of the document you
supplied. It is the anchor for everything downstream: two snapshots with the
same hash are the same input, byte for byte after canonicalisation, and two
with different hashes are not, however similar they look.

### Reading the choices in that document

**Ratings above demand.** Every node in the chain is 1.2 MW against a 1 MW
load. The 200 kW of headroom does nothing in this model. It is not reserve, it
is not margin, and no metric reports it. It exists so that chapter 14 can
change one rating and show what happens when headroom disappears.

**The load edge is rated at the load, not the path.** `pdu-a-to-load-1` is
1,000,000 W while everything upstream is 1,200,000 W. In a single-path design
that is invisible. In a dual-cord design it is the decision that determines
whether one cord alone can carry the whole load, and chapter 5 depends on it.

**The load is tagged `shared`.** Loads are terminal and never count as source
paths, so their path tag has no effect on redundancy evidence. Tagging them
`shared` is a convention, not a requirement.

**The redundancy group is documentation.** `{"mode": "N", "members":
["utility-a"]}` is recorded, hashed, and then ignored by the solver. It adds no
capacity, permits no transfer, and does not influence the reported redundancy
state. Declaring `"mode": "TWO_N"` on a topology with one feed would validate
happily and change nothing. Chapter 5 shows a run where the declared group and
the reported state disagree.

## Stage two: the redundant pair

Now add a second complete path and give the load a second cord. The A side is
unchanged, character for character. The additions are five components
(`utility-b`, `switchgear-b`, `ups-b`, `pdu-b`) and four connections, of which
the last is the second cord:

```json
    { "id": "utility-b", "label": "Synthetic utility B", "kind": "utility",
      "path": "B", "capacity_w": 1200000, "initial_status": "available" },
    { "id": "switchgear-b", "label": "Synthetic switchgear B", "kind": "switchgear",
      "path": "B", "capacity_w": 1200000, "initial_status": "available" },
    { "id": "ups-b", "label": "Synthetic UPS B", "kind": "ups",
      "path": "B", "capacity_w": 1200000, "initial_status": "available",
      "usable_energy_mj": 108000000000, "low_energy_threshold_pct": 25 },
    { "id": "pdu-b", "label": "Synthetic PDU B", "kind": "pdu",
      "path": "B", "capacity_w": 1200000, "initial_status": "available" }
```

```json
    { "id": "utility-b-to-switchgear-b", "from_component": "utility-b",
      "to_component": "switchgear-b", "capacity_w": 1200000, "initial_closed": true },
    { "id": "switchgear-b-to-ups-b", "from_component": "switchgear-b",
      "to_component": "ups-b", "capacity_w": 1200000, "initial_closed": true },
    { "id": "ups-b-to-pdu-b", "from_component": "ups-b",
      "to_component": "pdu-b", "capacity_w": 1200000, "initial_closed": true },
    { "id": "pdu-b-to-load-1", "from_component": "pdu-b",
      "to_component": "it-load-1", "capacity_w": 1000000, "initial_closed": true }
```

Change `snapshot_id` to `guide-2n`, set the redundancy group to
`{"id": "source-2n", "mode": "TWO_N", "members": ["utility-a", "utility-b"]}`,
and validate:

```powershell
dc-twin validate-design guide-2n.snapshot.json
```

```json
{"hash": "c6c6f02446315f5a99e46df429d6a9575784f0bfb72a0878a862551a0f97b98b", "snapshot_id": "guide-2n", "valid": true}
```

### What the second cord means, and does not

Both cords are `initial_closed: true` and each is rated 1,000,000 W, so either
one alone can carry the full load. That is what makes this a 2N arrangement in
the model's terms.

It is not what makes it a 2N arrangement in reality. In reality a dual-cord
load draws roughly half its power from each cord and the two supplies are
independent. In this model the solver takes the shortest augmenting path it
finds and puts as much flow on it as it can. Run any scenario against this
snapshot and look at the first segment, before any event has fired:

```text
--- segment 0-1000  state=two_n
   source_power_w : {"utility-a": 1000000, "utility-b": 0}
   flows>0        : {"pdu-a-to-load-1": 1000000, "switchgear-a-to-ups-a": 1000000,
                     "ups-a-to-pdu-a": 1000000, "utility-a-to-switchgear-a": 1000000}
```

Utility A carries the entire 1 MW and utility B carries nothing. That is a
*feasible* allocation, not a *predicted* one. Chapter 11 returns to this: the
flow figures answer "can capacity reach the load", never "how much current will
actually be on this cord".

The bundled `reference-2n` snapshot avoids the appearance of the problem by a
modelling trick worth knowing: it gives each load two 400 kW normal cords and
two 400 kW transfer cords, so the ratings themselves force an 800 kW load into
a 400/400 split. If you want a balanced-looking allocation in dc-twin, you get
it by constraining the edge ratings, not by asking the solver for it.

## Growing it further

The same two moves extend the example:

- **Add a generator.** Give it `"kind": "generator"` and a `start_delay_ms`,
  connect it to an ATS alongside the utility, and leave its connection
  `initial_closed: false`. It contributes nothing until a scenario declares it
  running, and chapter 7 covers the rules that govern when it may.
- **Add reserve equipment.** The bundled `reference-n-plus-1` snapshot puts
  three 800 kW UPS units between an input and an output switchgear, with the
  third UPS's input *and* output connections both open. That is how a reserve
  unit is expressed: present in the graph, rated, and disconnected until a
  transfer event closes it.

What you cannot do is add a third independent path. `path` accepts only `A`,
`B` and `shared`, and chapter 5 explains what that costs.

## Limits on size

Before you scale a topology up, the bounded envelope applies: at most 250
components, 500 connections, 100 redundancy groups, and 50 assumptions per
snapshot; 1 MiB decoded per document. These are checked before simulation
starts and are reported as `contract.*_limit` errors.

---

Previous: [2. Model concepts](02-model-concepts.md) ·
Next: [4. Loads and capacity](04-loads-and-capacity.md)
