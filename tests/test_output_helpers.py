"""Synthetic tests for output.py helper functions.

No real PST/EML/PDF files are used. All tests run in-process.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pst_to_pdf.output import (
    format_bytes,
    format_elapsed,
    green,
    red,
    set_color,
    yellow,
)


class TestFormatBytes(unittest.TestCase):
    def test_bytes(self):
        self.assertEqual(format_bytes(512), "512.0 B")

    def test_kilobytes(self):
        result = format_bytes(1024)
        self.assertEqual(result, "1.0 KB")

    def test_megabytes(self):
        result = format_bytes(2 * 1024 * 1024)
        self.assertEqual(result, "2.0 MB")

    def test_gigabytes(self):
        result = format_bytes(1.5 * 1024 ** 3)
        self.assertIn("1.5", result)
        self.assertIn("GB", result)

    def test_zero(self):
        self.assertEqual(format_bytes(0), "0.0 B")


class TestFormatElapsed(unittest.TestCase):
    def test_seconds_only(self):
        self.assertEqual(format_elapsed(45), "00:00:45")

    def test_minutes_and_seconds(self):
        self.assertEqual(format_elapsed(90), "00:01:30")

    def test_hours(self):
        self.assertEqual(format_elapsed(3661), "01:01:01")

    def test_zero(self):
        self.assertEqual(format_elapsed(0), "00:00:00")


class TestColorHelpers(unittest.TestCase):
    def setUp(self):
        set_color(True)

    def tearDown(self):
        # Reset to auto-detect after each test
        from pst_to_pdf import output as _out
        _out._color_override = None

    def test_green_contains_ansi(self):
        result = green("PASS")
        self.assertIn("\033[", result)
        self.assertIn("PASS", result)

    def test_yellow_contains_ansi(self):
        result = yellow("WARN")
        self.assertIn("\033[", result)
        self.assertIn("WARN", result)

    def test_red_contains_ansi(self):
        result = red("FAIL")
        self.assertIn("\033[", result)
        self.assertIn("FAIL", result)

    def test_no_color_strips_ansi(self):
        set_color(False)
        self.assertEqual(green("PASS"), "PASS")
        self.assertEqual(yellow("WARN"), "WARN")
        self.assertEqual(red("FAIL"), "FAIL")

    def test_no_color_env(self):
        from pst_to_pdf import output as _out
        _out._color_override = None  # force auto-detect
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            self.assertEqual(green("PASS"), "PASS")


class TestCopyFileWithProgress(unittest.TestCase):
    """Integration test using small dummy files in /tmp."""

    def test_copy_small_file(self):
        from pst_to_pdf.cli import _copy_file_with_progress

        with tempfile.TemporaryDirectory(prefix="pst_cli_test_") as tmpdir:
            src = Path(tmpdir) / "dummy.pst"
            dst = Path(tmpdir) / "copy.pst"
            data = b"X" * 1024  # 1 KB
            src.write_bytes(data)

            import time
            written = _copy_file_with_progress(src, dst, 1, 1, 0, len(data), time.monotonic())

            self.assertTrue(dst.exists())
            self.assertEqual(dst.read_bytes(), data)
            self.assertEqual(written, len(data))

    def test_copy_preserves_content(self):
        from pst_to_pdf.cli import _copy_file_with_progress

        with tempfile.TemporaryDirectory(prefix="pst_cli_test_") as tmpdir:
            src = Path(tmpdir) / "fake.pst"
            dst = Path(tmpdir) / "fake_copy.pst"
            # 6 MB to exercise the chunked read path
            data = bytes(range(256)) * (6 * 1024 * 4)
            src.write_bytes(data)

            import time
            written = _copy_file_with_progress(src, dst, 1, 1, 0, len(data), time.monotonic())

            self.assertEqual(written, len(data))
            self.assertEqual(dst.read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
