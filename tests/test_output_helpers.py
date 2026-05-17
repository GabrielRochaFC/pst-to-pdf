"""Synthetic tests for output.py helper functions.

No real PST/EML/PDF files are used. All tests run in-process.
"""

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pst_to_pdf.output import (
    finish_dynamic_line,
    format_bytes,
    format_elapsed,
    green,
    red,
    set_color,
    write_dynamic_line,
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


class TestDynamicLineHelpers(unittest.TestCase):
    def test_write_dynamic_line_non_tty_prints_text(self):
        """On non-TTY stdout, write_dynamic_line prints a normal line."""
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            write_dynamic_line("progress: 50%")
        self.assertIn("progress: 50%", buf.getvalue())

    def test_write_dynamic_line_non_tty_no_clear_sequence(self):
        """Non-TTY output must not contain ANSI clear-line escape."""
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            write_dynamic_line("some text")
        self.assertNotIn("\033[K", buf.getvalue())

    def test_finish_dynamic_line_non_tty_is_noop(self):
        """finish_dynamic_line must not output anything on non-TTY."""
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            finish_dynamic_line()
        self.assertEqual(buf.getvalue(), "")

    def test_shorter_line_after_longer_line(self):
        """Successive write_dynamic_line calls on non-TTY produce separate lines."""
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            write_dynamic_line("a long progress line with lots of text")
            write_dynamic_line("short")
        lines = buf.getvalue().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("short", lines[1])

    def test_extraction_progress_line_does_not_crash(self):
        """Simulate an extraction progress update without real readpst."""
        from pst_to_pdf.output import format_bytes, format_elapsed
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            write_dynamic_line(
                f"[test-slug] Extracting PST"
                f" | elapsed {format_elapsed(61)}"
                f" | EML files 1,234"
                f" | size {format_bytes(512 * 1024 * 1024)}"
            )
            finish_dynamic_line()
        output = buf.getvalue()
        self.assertIn("test-slug", output)
        self.assertIn("1,234", output)


class TestExtractionProgressWithDummyFiles(unittest.TestCase):
    def test_eml_tree_snapshot_on_fake_files(self):
        """eml_tree_snapshot works correctly on a temporary directory with fake .eml files."""
        from pst_to_pdf.extraction import eml_tree_snapshot

        with tempfile.TemporaryDirectory(prefix="pst_extract_test_") as tmpdir:
            root = Path(tmpdir)
            # Create 3 fake .eml files
            for i in range(3):
                f = root / f"msg{i}.eml"
                f.write_bytes(b"fake eml content " * 100)

            # Create a non-.eml file that should be ignored
            (root / "readme.txt").write_text("ignore me")

            snapshot = eml_tree_snapshot(root)

        self.assertEqual(snapshot.count, 3)
        self.assertGreater(snapshot.total_size, 0)
        self.assertGreater(snapshot.newest_mtime, 0)

    def test_eml_tree_snapshot_empty_dir(self):
        from pst_to_pdf.extraction import eml_tree_snapshot

        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot = eml_tree_snapshot(Path(tmpdir))

        self.assertEqual(snapshot.count, 0)
        self.assertEqual(snapshot.total_size, 0)


if __name__ == "__main__":
    unittest.main()
