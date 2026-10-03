import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.cache import CachedService


class CacheTests(unittest.TestCase):
    def test_failed_refresh_returns_last_success_as_stale(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = CachedService("example", Path(folder), ttl_seconds=0)
            fresh = cache.get(lambda: {"value": 42}, {})
            self.assertEqual(fresh["data"]["value"], 42)
            self.assertFalse(fresh["meta"]["stale"])

            stale = cache.get(lambda: (_ for _ in ()).throw(RuntimeError("offline")), {})
            self.assertEqual(stale["data"]["value"], 42)
            self.assertTrue(stale["meta"]["stale"])

    def test_failed_first_fetch_is_safe(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = CachedService("example", Path(folder), ttl_seconds=60)
            result = cache.get(lambda: (_ for _ in ()).throw(RuntimeError("offline")), {"value": None})
            self.assertEqual(result["data"], {"value": None})
            self.assertFalse(result["meta"]["available"])

    def test_allow_stale_returns_immediately_without_fetching(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = CachedService("example", Path(folder), ttl_seconds=0)
            cache.get(lambda: {"value": 42}, {})
            fetch = unittest.mock.Mock(side_effect=RuntimeError("must not run"))

            result = cache.get(fetch, {}, allow_stale=True)

            self.assertEqual(result["data"], {"value": 42})
            self.assertTrue(result["meta"]["stale"])
            fetch.assert_not_called()

    def test_non_persistent_fetch_never_writes_demo_data(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = CachedService("example", Path(folder), ttl_seconds=60)
            result = cache.get(
                lambda: {"value": "demo"}, {}, persist_success=False
            )
            self.assertEqual(result["data"], {"value": "demo"})
            self.assertFalse((Path(folder) / "example.json").exists())


if __name__ == "__main__":
    unittest.main()
