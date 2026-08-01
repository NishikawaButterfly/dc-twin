from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from dc_twin.cli import main
from tests.helpers import EXAMPLES


class CliTests(unittest.TestCase):
    def test_validate_run_replay_compare_and_overwrite_guard(self) -> None:
        design = EXAMPLES / "reference-2n.snapshot.json"
        scenario = EXAMPLES / "scenarios" / "healthy.scenario.json"
        with tempfile.TemporaryDirectory() as directory:
            result_path = Path(directory) / "result.json"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["validate-design", str(design)]), 0)
                self.assertEqual(main(["validate-scenario", str(design), str(scenario)]), 0)
                self.assertEqual(
                    main(
                        [
                            "run",
                            str(design),
                            str(scenario),
                            "--output",
                            str(result_path),
                        ]
                    ),
                    0,
                )
                self.assertEqual(main(["replay", str(design), str(scenario), str(result_path)]), 0)
                self.assertEqual(main(["compare", str(result_path), str(result_path)]), 0)
            value = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(value["metrics"]["unserved_energy_mj"], 0)
            with (
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(
                    main(
                        [
                            "run",
                            str(design),
                            str(scenario),
                            "--output",
                            str(result_path),
                        ]
                    ),
                    2,
                )
                self.assertEqual(
                    main(
                        [
                            "run",
                            str(design),
                            str(scenario),
                            "--output",
                            str(result_path),
                            "--force",
                        ]
                    ),
                    0,
                )

    def test_non_loopback_server_binding_is_rejected(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            # The wildcard address is the input under test; the CLI must refuse to bind it.
            self.assertEqual(main(["serve", "--host", "0.0.0.0"]), 2)  # noqa: S104


if __name__ == "__main__":
    unittest.main()
