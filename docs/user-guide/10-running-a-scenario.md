# 10. Running a scenario

There are three ways to run a scenario, and they are not equivalent. The CLI
runs anything you author. The API and the web explorer run only the five
bundled fixtures. Choose accordingly.

| | CLI | API | Web explorer |
|---|---|---|---|
| Your own topology | yes | no | no |
| Your own scenario | yes | no | no |
| Bundled fixtures | yes | yes | yes |
| Full result JSON | yes | yes | download |
| Telemetry CSV | no | yes | download |
| Replay verification | yes | yes | yes |
| Compare two runs | metrics only | no | side by side |
| Retains runs | files you write | in memory or PostgreSQL | no |

## Installing

Python 3.12 or newer. Install into a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test]"
```

Confirm the engine version before comparing anything to this guide:

```powershell
dc-twin validate-design examples/synthetic/reference-2n.snapshot.json
```

```json
{"hash": "56b8365e147fafdc4834152664f19af00bbc381a593ebbde06ed533d6283e27f", "snapshot_id": "reference-2n", "valid": true}
```

## The CLI

Six subcommands: `validate-design`, `validate-scenario`, `run`, `replay`,
`compare`, `serve`. Every one writes a single line of JSON to stdout on
success, a single line of JSON to stderr on failure, and communicates outcome
through the exit code.

### Exit codes

| Code | Meaning |
|---:|---|
| 0 | Success |
| 1 | Resource-limit rejection, and other errors not covered below |
| 2 | Contract or topology rejection |
| 3 | Internal invariant failure |
| 4 | Filesystem operation failed |
| 5 | Replay hash mismatch |

Note that resource-limit rejections exit 1 while contract rejections exit 2,
which is worth knowing if you are branching on exit codes in a script. Branch
on `error_code` from the JSON body instead; it is the stable contract.

### The four analysis commands

```powershell
dc-twin validate-design guide-2n.snapshot.json
dc-twin validate-scenario guide-2n.snapshot.json maint-overlap.scenario.json
dc-twin run guide-2n.snapshot.json maint-overlap.scenario.json --output results/maint.json
dc-twin replay guide-2n.snapshot.json maint-overlap.scenario.json results/maint.json
```

`run` requires `--output` and refuses to overwrite:

```json
{"detail": "Refusing to overwrite C:\\...\\results\\maint.json; pass --force explicitly.", "error_code": "output.exists"}
```

Pass `--force` when you mean it. The write is atomic — the engine writes to a
temporary file in the destination directory, fsyncs it, and renames it into
place — so an interrupted run never leaves a half-written result.

The success line carries the three things you will want:

```json
{"computation_hash": "5ae8c11939145806c5d794ebb6777c734e0d0448c9155305aef8b1a8d4700a39", "output": "C:\\...\\results\\maint.json", "run_id": "run-5ae8c11939145806"}
```

The `run_id` is content-addressed: `run-` plus the first 16 hex characters of
the computation hash. Two runs with the same ID are the same computation.

### Reading the result file

The result is a single JSON document with 14 top-level fields:

```text
schema_id, schema_version, engine_version,
run_id, snapshot_hash, scenario_hash, computation_hash,
scenario, metrics, timeline, transitions, alarms, telemetry, explanations
```

It is written sorted and indented, so it diffs cleanly in version control. It
is also large: the ten-minute composite reference run at 1,000 ms resolution
produces 600 timeline segments and 5,790 telemetry points.

For reading it interactively, extract what you need:

```powershell
python -c "import json; d=json.load(open('results/maint.json')); print(json.dumps(d['metrics'], indent=1, sort_keys=True))"
```

```json
{
 "demanded_energy_mj": 600000000000,
 "interruption_count": 1,
 "interruption_duration_ms": 72000,
 "minimum_served_w": 0,
 "modeled_redundancy_state": "no_path",
 "peak_demand_w": 1000000,
 "peak_served_w": 1000000,
 "peak_stranded_capacity_w": 1000000,
 "served_energy_mj": 528000000000,
 "service_ratio_ppm": 880000,
 "unserved_energy_mj": 72000000000
}
```

## The API

Start it on loopback:

```powershell
dc-twin serve --host 127.0.0.1 --port 8099
```

The CLI refuses any non-loopback host:

```json
{"detail": "The CLI binds to loopback only; use a hardened reverse proxy for deployment.", "error_code": "server.non_loopback_host"}
```

For anything beyond a local session, use the container workflow in
[OPERATIONS.md](../OPERATIONS.md). The reference API has no authentication and
must not be exposed to an untrusted network.

### The routes you will use

Full documentation is in [API.md](../API.md). In analysis terms there are five.

**Catalog.** `GET /api/v1/reference-scenarios` lists the five allowlisted
fixtures with their labels, horizons and event counts. The response also
carries the standing disclaimer:

```text
Deterministic active-power capacity simulation; not AC power flow, protection,
safety, control, or certification.
```

**Run.** `POST /api/v1/reference-scenarios/{scenario_id}/runs` with no body.
Running `REF-DC-2N-001` returns the complete result envelope:

```text
  run_id            run-71c0ef262cfc15d0
  computation_hash  71c0ef262cfc15d0fd449b53adcbad62c8c51418ab33d211f64031e01c77b5a0
```

That is character for character the hash the CLI produces for the same fixture.
The two interfaces run the same kernel and agree exactly, which is the point.

**Retrieve.** `GET /api/v1/runs/{run_id}` returns the retained payload. It is
byte-identical to the payload the `POST` returned. Run IDs are locators, not
credentials.

**Replay.** `POST /api/v1/runs/{run_id}/replay` recomputes and compares:

```json
{"run_id": "run-71c0ef262cfc15d0", "expected_computation_hash": "71c0ef262cfc15d0fd449b53adcbad62c8c51418ab33d211f64031e01c77b5a0", "actual_computation_hash": "71c0ef262cfc15d0fd449b53adcbad62c8c51418ab33d211f64031e01c77b5a0", "matches": true, "replay_run_id": "run-71c0ef262cfc15d0"}
```

**Telemetry.** `GET /api/v1/runs/{run_id}/telemetry.csv` is the only export
format the tool offers, and it exists only on the API:

```text
sequence,time_ms,component_id,metric,value,unit,quality,state_hash
0,1000,system,demand_w,1600000,W,synthetic,362778558f48e21606829577e060f126e1568b80eb4c0b718db4d2f9502f2f40
1,1000,system,served_w,1600000,W,synthetic,362778558f48e21606829577e060f126e1568b80eb4c0b718db4d2f9502f2f40
```

Every row carries `quality=synthetic`. The composite reference run yields 5,790
rows. If you want the timeline in a spreadsheet, this is the route — but note
what it is: a point stream of per-component values at segment end times, not
the timeline table. There is no CSV export of segments, metrics or alarms.

### Errors

Failures return RFC 9457 Problem Details with `application/problem+json`:

```json
{"detail": "No allowlisted synthetic scenario is named 'NOT-A-SCENARIO'.", "error_code": "reference.scenario_not_found", "instance": "/api/v1/reference-scenarios/NOT-A-SCENARIO/runs", "request_id": "40d01a4f-fd01-4fb1-a90d-bf7a0a6b6f4b", "status": 404, "title": "Reference scenario not found", "type": "https://github.com/NishikawaButterfly/dc-twin/blob/main/docs/API.md#problem-details"}
```

Branch on `status` and `error_code`. Log `request_id` — every response carries
it in an `X-Request-ID` header too, and a client-supplied one is echoed back.

### Health

```powershell
curl http://127.0.0.1:8099/health/live
curl http://127.0.0.1:8099/health/ready
```

```json
{"status": "live", "engine_version": "1.0.0"}
{"status": "ready", "engine_version": "1.0.0"}
```

`/health/live` is process-level and does not test the database. `/health/ready`
does. Use `/health/live` to confirm which engine version produced a result you
are holding.

## The web explorer

The API serves a dependency-free page at its root. Open
`http://127.0.0.1:8099/` after `dc-twin serve`, or use the public instance at
`https://dc-twin.fly.dev/`.

The layout, top to bottom:

**Select and run.** A dropdown of the five fixtures, each annotated with its
catalogue redundancy note, plus the scenario description, duration and event
count. Three buttons: *Run scenario*, *Replay and verify*, and — in a separate
panel — *Compare runs* against two scenario selectors.

**Five KPI tiles.** Demanded energy, served energy, unserved energy, scenario
service ratio, and modeled redundancy state, each with a permanent caveat line
and a "Why this value?" expander carrying the engine's own explanation text.
Running `REF-DC-2N-001` gives:

```text
Demanded energy           266.67 kWh   Across this modeled scenario only
Served energy             252.44 kWh   Delivered by modeled available paths
Unserved energy            14.22 kWh   Demand not served in this scenario
Scenario service ratio       94.67%    Not a site-availability or SLA claim
Modeled redundancy state    No path    Scenario state, not certification
```

Those caveat lines are not decoration. They are the shortest correct reading of
each number, and chapter 19 expands every one of them.

**Timeline position.** A slider across the segments, with the topology diagram,
the served-versus-unserved chart and the aggregate UPS energy gauge all
following it. Dragging through the composite run:

```text
Step   1/600 at T+00:00. Reported modeled state: 2N.
Step 101/600 at T+01:40. Reported modeled state: Single path.
Step 201/600 at T+03:20. Reported modeled state: Battery backed.
Step 392/600 at T+06:31. Reported modeled state: No path.
Step 426/600 at T+07:05. Reported modeled state: Single path.
```

This is the explorer's real strength: it is the fastest way to find *where* in
a run the state changed, before going to the JSON for the exact figures.

**Events and alarms.** A merged, time-ordered table of transitions and alarms:

```text
T+01:02 | Transition | Maintenance start        | pdu-b       | Modeled state transition.
T+01:02 | Alarm      | Info                     | pdu-b       | pdu-b entered planned maintenance.
T+02:00 | Alarm      | Critical                 | utility-a   | utility-a entered the modeled failed state.
T+06:30 | Alarm      | Critical                 | ups-a       | ups-a exhausted its modeled usable battery energy.
T+06:30 | Alarm      | Critical                 | System      | Modeled unserved load increased to 1600000 W.
```

One caution: **this table shows alarms raised and never shows alarms cleared.**
The composite run clears `maintenance_active` at 420,000 ms and `load_unserved`
at 422,000 ms, and neither clearance appears. From the table alone you cannot
tell which alarms were still active at the end of the run. The clearances are
in the result JSON, under `transitions[].alarms_cleared`.

**Run provenance.** Run ID, engine version, and all three hashes, with the
correct framing beside them: a matching hash supports reproducibility; it does
not validate real-world equipment or operation.

**Downloads.** *Result JSON* and *Telemetry CSV*.

### What the explorer cannot do

It cannot load your topology. It cannot load your scenario. It cannot edit an
event, change a rating, or re-run anything with a modified input. It is a
viewer for five fixed fixtures.

That is a deliberate security boundary, documented in
[THREAT_MODEL.md](../THREAT_MODEL.md): the API accepts no arbitrary topology,
so a public instance cannot be used to run someone's real site data through a
tool that would then publish it. It also means that all of the analysis in this
guide — every custom topology, every deliberate case — is CLI work.

---

Previous: [9. Creating a scenario](09-creating-a-scenario.md) ·
Next: [11. Reading the timeline](11-reading-the-timeline.md)
