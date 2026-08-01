# Read-only simulation UI

This directory contains the dependency-free web interface for the Data Center Electrical Digital Twin. Serve it from the same origin as the API so the strict content-security policy and relative API routes work without cross-origin configuration.

The interface is intentionally read-only: it lists synthetic reference scenarios, requests a deterministic run, replays it for hash comparison, and downloads evidence already returned by the API. It has no topology editor, uploads, live telemetry, or control commands.

## API contract used by the client

- `GET /api/v1/reference-scenarios`
- `POST /api/v1/reference-scenarios/{scenario_id}/runs` with no request body

Preferred scenario-list response:

```json
{
  "scenarios": [
    {
      "scenario_id": "n-plus-one-generator-loss",
      "label": "N+1 generator loss",
      "description": "Synthetic reference scenario.",
      "modeled_redundancy": "N+1",
      "horizon_ms": 900000,
      "event_count": 3
    }
  ]
}
```

Preferred run response fields are:

- Provenance: `run_id`, `computation_hash`, `snapshot_hash`, `scenario_hash`, and `engine_version`.
- Context: `scenario` with `scenario_id`, `label`, and `horizon_ms`.
- Scenario metrics: `metrics.demanded_energy_mj`, `served_energy_mj`, `unserved_energy_mj`, `service_ratio_ppm`, `peak_demand_w`, `peak_served_w`, and `modeled_redundancy_state`.
- Timeline: `timeline[]` with `start_ms`, `end_ms`, `demand_w`, `served_w`, `unserved_w`, `redundancy_state`, `battery_energy_mj`, `source_power_w`, `load_service_w`, `connection_flow_w`, `state_hash`, and `causal_event_ids`.
- Evidence: `transitions[]`, `alarms[]`, and `telemetry[]`.
- Metric rationale: optional `explanations` keyed by metric name.

The client converts the contract's integer `W`, `mJ`, and `ms` values to human-readable `kW`, `kWh`, and elapsed time. It also tolerates common aliases and missing optional fields. Missing evidence is shown explicitly; it is never invented. Telemetry rows follow the result contract's `sequence`, `time_ms`, `component_id`, `metric`, `value`, `unit`, `quality`, and `state_hash` shape. The JSON and CSV downloads are built locally from the exact run response.

## Local serving

The production application should mount this directory as static assets and serve `index.html` for `/`. For a visual-only check, serve the repository root with any static HTTP server; API calls will show the designed error state until a compatible same-origin API is available. Opening `index.html` directly as a `file:` URL is not supported.

## Product boundary

The UI describes only a deterministic synthetic active-power capacity model. It does not claim AC power-flow accuracy, protection or coordination analysis, equipment certification, design approval, site availability, SLA compliance, or live operational control.

Accessibility features include semantic landmarks and tables, keyboard-native controls, visible focus, text and symbols in addition to color, responsive layouts, reduced-motion support, high-contrast support, and assistive-technology status announcements. API-provided text is inserted with `textContent`; it is not interpreted as HTML.
