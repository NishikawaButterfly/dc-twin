from __future__ import annotations

import importlib.util
import unittest

HAS_API = importlib.util.find_spec("fastapi") is not None

if HAS_API:
    from fastapi.testclient import TestClient

    from dc_twin.api import app


@unittest.skipUnless(HAS_API, "FastAPI test dependencies are not installed")
class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)

    def test_health_catalog_run_get_replay_and_csv(self) -> None:
        live = self.client.get("/health/live")
        self.assertEqual(live.status_code, 200)
        self.assertEqual(live.headers["x-content-type-options"], "nosniff")
        self.assertNotIn("access-control-allow-origin", live.headers)
        self.assertEqual(self.client.get("/health/ready").status_code, 200)

        catalog = self.client.get("/api/v1/reference-scenarios")
        self.assertEqual(catalog.status_code, 200)
        scenarios = catalog.json()["scenarios"]
        self.assertEqual(len(scenarios), 3)
        scenario_id = next(
            item["scenario_id"] for item in scenarios if item["scenario_id"] == "REF-DC-2N-001"
        )
        run = self.client.post(f"/api/v1/reference-scenarios/{scenario_id}/runs")
        self.assertEqual(run.status_code, 200)
        result = run.json()
        run_id = result["run_id"]
        self.assertEqual(self.client.get(f"/api/v1/runs/{run_id}").json(), result)
        replay = self.client.post(f"/api/v1/runs/{run_id}/replay")
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["matches"])
        export = self.client.get(f"/api/v1/runs/{run_id}/telemetry.csv")
        self.assertEqual(export.status_code, 200)
        self.assertTrue(export.text.startswith("sequence,time_ms,component_id"))
        self.assertIn("attachment", export.headers["content-disposition"])

    def test_problem_details_do_not_expose_stack_traces(self) -> None:
        response = self.client.post("/api/v1/reference-scenarios/not-available/runs")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers["content-type"], "application/problem+json")
        body = response.json()
        self.assertEqual(body["error_code"], "reference.scenario_not_found")
        self.assertIn("request_id", body)
        self.assertNotIn("traceback", str(body).lower())

    def test_static_interface_is_served(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Electrical Digital Twin", response.text)

    def test_static_assets_carry_executable_media_types(self) -> None:
        # Every response is nosniff, so a text/plain guess (seen on Windows,
        # where mimetypes reads the registry) makes the browser refuse app.js.
        script = self.client.get("/app.js")
        self.assertEqual(script.status_code, 200)
        self.assertIn("javascript", script.headers["content-type"])
        styles = self.client.get("/styles.css")
        self.assertEqual(styles.status_code, 200)
        self.assertIn("text/css", styles.headers["content-type"])


if __name__ == "__main__":
    unittest.main()
