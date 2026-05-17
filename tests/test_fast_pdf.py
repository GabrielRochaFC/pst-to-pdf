"""Synthetic tests for write_fast_pdf layout and header sanitization.

No real PST/EML/PDF case files are used.
"""

import importlib.util
import tempfile
import unittest
from pathlib import Path

from pst_to_pdf.converter import sanitize_header_value, write_fast_pdf

_REPORTLAB_AVAILABLE = importlib.util.find_spec("reportlab") is not None
_skip_no_reportlab = unittest.skipUnless(_REPORTLAB_AVAILABLE, "reportlab not installed")


def _sample_metadata(**overrides: str) -> dict[str, str]:
    base = {
        "Subject": "Test email subject",
        "From": "sender@example.com",
        "To": "recipient@example.com",
        "Cc": "",
        "Bcc": "",
        "Date": "Mon, 01 Jan 2024 12:00:00 +0000",
        "Message-ID": "<test-12345@example.com>",
        "Source EML path": "/tmp/test.eml",
        "Attachment filenames": "",
    }
    base.update(overrides)
    return base


class TestSanitizeHeaderValue(unittest.TestCase):
    def test_crlf_collapsed_to_space(self):
        result = sanitize_header_value("John Doe\r\n<john@example.com>")
        self.assertNotIn("\r", result)
        self.assertNotIn("\n", result)
        self.assertIn("John Doe", result)
        self.assertIn("john@example.com", result)

    def test_lf_collapsed(self):
        result = sanitize_header_value("line1\nline2")
        self.assertNotIn("\n", result)
        self.assertIn("line1", result)
        self.assertIn("line2", result)

    def test_tab_collapsed(self):
        result = sanitize_header_value("Subject\twith\ttabs")
        self.assertNotIn("\t", result)

    def test_empty_value(self):
        self.assertEqual(sanitize_header_value(""), "")
        self.assertEqual(sanitize_header_value(None), "")  # type: ignore[arg-type]

    def test_plain_value_unchanged(self):
        self.assertEqual(sanitize_header_value("plain text"), "plain text")


@_skip_no_reportlab
class TestFastPDFLayout(unittest.TestCase):
    def test_basic_pdf_generated(self):
        with tempfile.TemporaryDirectory(prefix="pst_pdf_test_") as tmpdir:
            pdf_path = Path(tmpdir) / "basic.pdf"
            write_fast_pdf(pdf_path, _sample_metadata(), "Hello, this is the body text.")
            self.assertTrue(pdf_path.exists())
            self.assertGreater(pdf_path.stat().st_size, 0)

    def test_long_to_does_not_raise(self):
        """Very long To field must not cause ReportLab LayoutError."""
        long_to = ", ".join(f"recipient{i}@example.com" for i in range(200))
        with tempfile.TemporaryDirectory(prefix="pst_pdf_test_") as tmpdir:
            pdf_path = Path(tmpdir) / "long_to.pdf"
            write_fast_pdf(pdf_path, _sample_metadata(To=long_to), "Body text.")
            self.assertTrue(pdf_path.exists())
            self.assertGreater(pdf_path.stat().st_size, 0)

    def test_long_cc_does_not_raise(self):
        """Very long Cc field must not cause ReportLab LayoutError."""
        long_cc = ", ".join(f"cc{i}@example.com" for i in range(200))
        with tempfile.TemporaryDirectory(prefix="pst_pdf_test_") as tmpdir:
            pdf_path = Path(tmpdir) / "long_cc.pdf"
            write_fast_pdf(pdf_path, _sample_metadata(Cc=long_cc), "Body text.")
            self.assertTrue(pdf_path.exists())
            self.assertGreater(pdf_path.stat().st_size, 0)

    def test_crlf_in_headers_does_not_raise(self):
        """CR/LF inside header values must not break PDF generation."""
        messy_to = "John Doe\r\n<john@example.com>,\r\nJane Doe <jane@example.com>"
        with tempfile.TemporaryDirectory(prefix="pst_pdf_test_") as tmpdir:
            pdf_path = Path(tmpdir) / "crlf_header.pdf"
            write_fast_pdf(pdf_path, _sample_metadata(To=messy_to), "Body text.")
            self.assertTrue(pdf_path.exists())

    def test_empty_body_does_not_raise(self):
        with tempfile.TemporaryDirectory(prefix="pst_pdf_test_") as tmpdir:
            pdf_path = Path(tmpdir) / "empty_body.pdf"
            write_fast_pdf(pdf_path, _sample_metadata(), "")
            self.assertTrue(pdf_path.exists())

    def test_multiline_body_rendered(self):
        body = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        with tempfile.TemporaryDirectory(prefix="pst_pdf_test_") as tmpdir:
            pdf_path = Path(tmpdir) / "multiline.pdf"
            write_fast_pdf(pdf_path, _sample_metadata(), body)
            self.assertTrue(pdf_path.exists())
            self.assertGreater(pdf_path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
