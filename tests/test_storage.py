from __future__ import annotations

import unittest

from dc_twin.storage import MemoryRunStore


class MemoryStoreTests(unittest.TestCase):
    def test_results_are_copied_and_retention_is_bounded(self) -> None:
        store = MemoryRunStore(max_runs=1)
        first = {"run_id": "run-0000000000000000", "value": {"answer": 1}}
        store.save_run(first, snapshot={}, scenario={})
        first["value"]["answer"] = 2
        stored = store.get_run("run-0000000000000000")
        assert stored is not None
        self.assertEqual(stored["value"]["answer"], 1)
        stored["value"]["answer"] = 3
        self.assertEqual(store.get_run("run-0000000000000000")["value"]["answer"], 1)
        store.save_run({"run_id": "run-1111111111111111"}, snapshot={}, scenario={})
        self.assertIsNone(store.get_run("run-0000000000000000"))
        self.assertTrue(store.ready())


if __name__ == "__main__":
    unittest.main()
