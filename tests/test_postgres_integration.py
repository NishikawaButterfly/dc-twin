from __future__ import annotations

import os
import unittest

from dc_twin.engine import simulate
from dc_twin.reference import ReferenceCatalog
from dc_twin.storage import PostgresRunStore

DATABASE_URL = os.getenv("DC_TWIN_TEST_DATABASE_URL")


@unittest.skipUnless(DATABASE_URL, "PostgreSQL integration URL is not configured")
class PostgresStoreTests(unittest.TestCase):
    def test_immutable_idempotent_run_round_trip(self) -> None:
        assert DATABASE_URL is not None
        catalog = ReferenceCatalog.load()
        reference = catalog.scenarios["REF-DC-2N-001"]
        result = simulate(catalog.snapshot, reference.scenario)
        store = PostgresRunStore(DATABASE_URL)
        store.save_run(result, snapshot=catalog.snapshot_raw, scenario=reference.raw)
        store.save_run(result, snapshot=catalog.snapshot_raw, scenario=reference.raw)
        self.assertEqual(store.get_run(str(result["run_id"])), result)
        self.assertTrue(store.ready())


if __name__ == "__main__":
    unittest.main()
