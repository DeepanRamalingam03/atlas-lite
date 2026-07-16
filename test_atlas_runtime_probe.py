from __future__ import annotations

import unittest

from atlas_smoke.runtime_probe import atlas_runtime_probe


class TestAtlasRuntimeProbe(unittest.TestCase):
    def test_atlas_runtime_probe_returns_expected_value(self) -> None:
        expected = "atlas-runtime-ok"
        result = atlas_runtime_probe()
        self.assertEqual(expected, result)


if __name__ == "__main__":
    unittest.main()
