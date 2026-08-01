"""Versioned read-only FastAPI surface for allowlisted synthetic scenarios."""

from __future__ import annotations

import csv
import io
import mimetypes
import os
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from dc_twin.engine import ENGINE_VERSION, simulate, verify_replay
from dc_twin.errors import DCTwinError, InvalidParameter
from dc_twin.reference import ReferenceCatalog
from dc_twin.storage import MemoryRunStore, PostgresRunStore, RunStore

RUN_ID = re.compile(r"^run-[a-f0-9]{16}$")


def _store_from_environment() -> RunStore:
    database_url = os.getenv("DC_TWIN_DATABASE_URL")
    return PostgresRunStore(database_url) if database_url else MemoryRunStore(max_runs=100)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.catalog = ReferenceCatalog.load()
    app.state.store = _store_from_environment()
    yield


app = FastAPI(
    title="Data Center Electrical Digital Twin",
    version="0.1.0",
    description=(
        "Read-only deterministic capacity simulation for allowlisted synthetic electrical "
        "reference architectures. Not AC power flow, protection, control, or certification."
    ),
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/v1/openapi.json",
    lifespan=_lifespan,
)


@app.middleware("http")
async def security_headers(request: Request, call_next: Any) -> Response:
    request_id = request.headers.get("x-request-id", "")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", request_id):
        request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response: Response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; object-src 'none'; base-uri 'self'; form-action 'none'; "
        "frame-ancestors 'none'"
    )
    return response


def _problem(
    request: Request,
    *,
    status: int,
    title: str,
    detail: str,
    error_code: str,
    invalid_params: tuple[InvalidParameter, ...] = (),
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": "https://github.com/NishikawaButterfly/dc-twin/blob/main/docs/API.md#problem-details",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "error_code": error_code,
        "request_id": getattr(request.state, "request_id", "unavailable"),
    }
    if invalid_params:
        body["invalid_params"] = [
            {"name": parameter.name, "reason": parameter.reason} for parameter in invalid_params
        ]
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


@app.exception_handler(DCTwinError)
async def domain_error(request: Request, exc: DCTwinError) -> JSONResponse:
    return _problem(
        request,
        status=exc.status_code,
        title="Simulation request rejected",
        detail=exc.message,
        error_code=exc.code,
        invalid_params=exc.invalid_params,
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    parameters = tuple(
        InvalidParameter(
            name=".".join(str(part) for part in error["loc"]),
            reason=str(error["msg"]),
        )
        for error in exc.errors()
    )
    return _problem(
        request,
        status=422,
        title="Request validation failed",
        detail="One or more request fields are invalid.",
        error_code="api.validation_failed",
        invalid_params=parameters,
    )


def _catalog(request: Request) -> ReferenceCatalog:
    catalog: ReferenceCatalog = request.app.state.catalog
    return catalog


def _store(request: Request) -> RunStore:
    store: RunStore = request.app.state.store
    return store


@app.get("/health/live", tags=["health"])
def health_live() -> dict[str, str]:
    return {"status": "live", "engine_version": ENGINE_VERSION}


@app.get("/health/ready", tags=["health"])
def health_ready(request: Request) -> Response:
    if _store(request).ready():
        return JSONResponse({"status": "ready", "engine_version": ENGINE_VERSION})
    return JSONResponse({"status": "not_ready"}, status_code=503)


@app.get("/api/v1/reference-scenarios", tags=["reference scenarios"])
def list_reference_scenarios(request: Request) -> dict[str, Any]:
    return {
        "engine_version": ENGINE_VERSION,
        "data_classification": "synthetic",
        "disclaimer": (
            "Deterministic active-power capacity simulation; not AC power flow, protection, "
            "safety, control, or certification."
        ),
        "scenarios": _catalog(request).summaries(),
    }


@app.post(
    "/api/v1/reference-scenarios/{scenario_id}/runs",
    tags=["simulation runs"],
    response_model=None,
)
def run_reference_scenario(scenario_id: str, request: Request) -> dict[str, Any] | JSONResponse:
    catalog = _catalog(request)
    reference = catalog.scenarios.get(scenario_id)
    if reference is None:
        return _problem(
            request,
            status=404,
            title="Reference scenario not found",
            detail=f"No allowlisted synthetic scenario is named {scenario_id!r}.",
            error_code="reference.scenario_not_found",
        )
    result = simulate(catalog.snapshot, reference.scenario)
    _store(request).save_run(
        result,
        snapshot=catalog.snapshot_raw,
        scenario=reference.raw,
    )
    return result


@app.get("/api/v1/runs/{run_id}", tags=["simulation runs"], response_model=None)
def get_run(run_id: str, request: Request) -> dict[str, Any] | JSONResponse:
    if not RUN_ID.fullmatch(run_id):
        return _problem(
            request,
            status=404,
            title="Simulation run not found",
            detail="The requested run identifier is not available.",
            error_code="run.not_found",
        )
    result = _store(request).get_run(run_id)
    if result is None:
        return _problem(
            request,
            status=404,
            title="Simulation run not found",
            detail="The requested run is not retained by this instance.",
            error_code="run.not_found",
        )
    return result


@app.post("/api/v1/runs/{run_id}/replay", tags=["simulation runs"], response_model=None)
def replay_run(run_id: str, request: Request) -> dict[str, Any] | JSONResponse:
    existing = _store(request).get_run(run_id) if RUN_ID.fullmatch(run_id) else None
    if existing is None:
        return _problem(
            request,
            status=404,
            title="Simulation run not found",
            detail="The requested run is not retained by this instance.",
            error_code="run.not_found",
        )
    scenario_id = str(existing["scenario"]["scenario_id"])
    catalog = _catalog(request)
    reference = catalog.scenarios.get(scenario_id)
    if reference is None:
        return _problem(
            request,
            status=409,
            title="Replay input unavailable",
            detail="The run's immutable reference scenario is not available in this engine build.",
            error_code="replay.input_unavailable",
        )
    verification = verify_replay(
        catalog.snapshot,
        reference.scenario,
        str(existing["computation_hash"]),
    )
    return {"run_id": run_id, **verification}


@app.get("/api/v1/runs/{run_id}/telemetry.csv", tags=["simulation runs"], response_model=None)
def telemetry_csv(run_id: str, request: Request) -> Response | JSONResponse:
    existing = _store(request).get_run(run_id) if RUN_ID.fullmatch(run_id) else None
    if existing is None:
        return _problem(
            request,
            status=404,
            title="Simulation run not found",
            detail="The requested run is not retained by this instance.",
            error_code="run.not_found",
        )
    output = io.StringIO(newline="")
    fieldnames = [
        "sequence",
        "time_ms",
        "component_id",
        "metric",
        "value",
        "unit",
        "quality",
        "state_hash",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for record in existing.get("telemetry", []):
        writer.writerow({field: _csv_safe(record.get(field, "")) for field in fieldnames})
    return Response(
        output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{run_id}-telemetry.csv"'},
    )


def _csv_safe(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{value}"
    return value


def _web_root() -> Path:
    source = Path(__file__).resolve().parents[2] / "web"
    if source.is_dir():
        return source
    return Path(__file__).resolve().parent / "static"


web_root = _web_root()

# Windows can map .js to text/plain through the registry, and every response
# carries X-Content-Type-Options: nosniff, so a wrong guess makes the browser
# refuse to run the UI. Pin the types the web assets actually use.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")


@app.get("/", include_in_schema=False)
def web_index() -> FileResponse:
    return FileResponse(web_root / "index.html")


app.mount("/", StaticFiles(directory=web_root), name="web")
