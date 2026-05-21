"""Synthetic tests for processor.prepare_case_filter fingerprint behavior.

No real PST data. Uses temp case directories only.
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from pst_to_pdf.processor import (
    FILTER_FILE_RELPATH,
    FILTER_FINGERPRINT_RELPATH,
    prepare_case_filter,
)


class TestPrepareCaseFilter(unittest.TestCase):
    def test_first_run_writes_file_and_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            path = prepare_case_filter(case_dir, ["a@x.com", "B@Y.com"], force_filter=False)
            self.assertEqual(path, case_dir / FILTER_FILE_RELPATH)
            self.assertTrue(path.is_file())
            self.assertTrue((case_dir / FILTER_FINGERPRINT_RELPATH).is_file())
            self.assertEqual(
                path.read_text(encoding="utf-8").splitlines(),
                ["a@x.com", "b@y.com"],
            )

    def test_same_filter_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            prepare_case_filter(case_dir, ["a@x.com", "b@y.com"], force_filter=False)
            prepare_case_filter(case_dir, ["B@Y.com", "A@X.com"], force_filter=False)

    def test_changed_filter_aborts_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            prepare_case_filter(case_dir, ["a@x.com"], force_filter=False)
            with self.assertRaises(SystemExit) as ctx:
                prepare_case_filter(case_dir, ["a@x.com", "b@y.com"], force_filter=False)
            self.assertIn("Filter set differs", str(ctx.exception))

    def test_changed_filter_overrides_with_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            prepare_case_filter(case_dir, ["a@x.com"], force_filter=False)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                prepare_case_filter(case_dir, ["a@x.com", "b@y.com"], force_filter=True)
            self.assertIn("--force-filter overrides", buf.getvalue())
            self.assertEqual(
                (case_dir / FILTER_FILE_RELPATH).read_text(encoding="utf-8").splitlines(),
                ["a@x.com", "b@y.com"],
            )


if __name__ == "__main__":
    unittest.main()
