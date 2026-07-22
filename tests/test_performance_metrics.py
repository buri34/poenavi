import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from src.utils.performance_metrics import measure


class PerformanceMetricsTest(unittest.TestCase):
    @patch.dict(os.environ, {"POENAVI_PROFILE": "1"})
    @patch("src.utils.performance_metrics.perf_counter", side_effect=[1.0, 1.0125])
    def test_measure_prints_elapsed_milliseconds_when_enabled(self, _clock):
        output = io.StringIO()

        with redirect_stdout(output), measure("guide reload"):
            pass

        self.assertIn("[Performance] guide reload: 12.5 ms", output.getvalue())

    @patch.dict(os.environ, {}, clear=True)
    def test_measure_is_silent_when_disabled(self):
        output = io.StringIO()

        with redirect_stdout(output), measure("guide reload"):
            pass

        self.assertEqual(output.getvalue(), "")
