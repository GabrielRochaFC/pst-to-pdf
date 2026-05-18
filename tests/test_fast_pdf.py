"""Synthetic tests for write_fast_pdf layout, header sanitization, and EML path display.

No real PST/EML/PDF case files are used.
"""

import importlib.util
import tempfile
import unittest
from pathlib import Path

from pst_to_pdf.converter import display_eml_path, sanitize_header_value, write_fast_pdf

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


class TestDisplayEmlPath(unittest.TestCase):
    """Tests for display_eml_path — all use synthetic/fake paths only."""

    def test_relative_to_case_parent(self):
        """EML path inside case_dir is displayed relative to case_dir.parent."""
        case_dir = Path("/tmp/pst-cases/coordenacao-gestaoambiental-psts")
        eml_path = (
            case_dir
            / "output/coordenacao-gestaoambiental-001/eml"
            / "coordenacao.gestaoambiental@incra.gov.br.001"
            / "Top-of-Information-Store/Inbox/124.eml"
        )
        result = display_eml_path(eml_path, case_dir)
        expected = (
            "coordenacao-gestaoambiental-psts/output/coordenacao-gestaoambiental-001/eml"
            "/coordenacao.gestaoambiental@incra.gov.br.001"
            "/Top-of-Information-Store/Inbox/124.eml"
        )
        self.assertEqual(result, expected)

    def test_keeps_case_directory_name(self):
        """Displayed path starts with the case directory name, not just 'output/'."""
        case_dir = Path("/tmp/pst-cases/my-case-dir")
        eml_path = case_dir / "output/slug-001/eml/msg.eml"
        result = display_eml_path(eml_path, case_dir)
        self.assertTrue(
            result.startswith("my-case-dir/"),
            f"Expected path to start with 'my-case-dir/', got: {result!r}",
        )

    def test_does_not_start_with_output(self):
        """Displayed path must not start with 'output/' — case dir name must precede it."""
        case_dir = Path("/tmp/pst-cases/my-case")
        eml_path = case_dir / "output/slug/eml/msg.eml"
        result = display_eml_path(eml_path, case_dir)
        self.assertFalse(
            result.startswith("output/"),
            f"Path starts with 'output/' instead of case dir name: {result!r}",
        )

    def test_fallback_when_eml_outside_case_parent(self):
        """EML path not under case_dir.parent falls back to its absolute string."""
        case_dir = Path("/tmp/cases/my-case")
        eml_path = Path("/other/location/msg.eml")
        result = display_eml_path(eml_path, case_dir)
        self.assertEqual(result, str(eml_path))

    def test_fallback_when_no_case_dir(self):
        """None case_dir returns the absolute path unchanged."""
        eml_path = Path("/some/absolute/path/msg.eml")
        result = display_eml_path(eml_path, None)
        self.assertEqual(result, str(eml_path))

    def test_eml_exactly_in_case_parent_sibling(self):
        """An EML that lives in a sibling of case_dir falls back gracefully."""
        case_dir = Path("/tmp/cases/case-a")
        eml_path = Path("/tmp/cases/case-b/output/slug/eml/msg.eml")
        # case-b is a sibling of case-a; it IS under case_dir.parent (/tmp/cases)
        result = display_eml_path(eml_path, case_dir)
        self.assertTrue(result.startswith("case-b/"))


@_skip_no_reportlab
class TestFastPDFNoTitle(unittest.TestCase):
    def test_generated_pdf_does_not_embed_old_title(self):
        """PDF generated after title removal must still be a valid non-empty file."""
        with tempfile.TemporaryDirectory(prefix="pst_pdf_notitle_") as tmpdir:
            pdf_path = Path(tmpdir) / "notitle.pdf"
            write_fast_pdf(pdf_path, _sample_metadata(), "Body text.")
            self.assertTrue(pdf_path.exists())
            self.assertGreater(pdf_path.stat().st_size, 0)

    def test_metadata_only_email_renders(self):
        """Empty body must not crash when the title is absent."""
        with tempfile.TemporaryDirectory(prefix="pst_pdf_notitle_") as tmpdir:
            pdf_path = Path(tmpdir) / "empty_body_notitle.pdf"
            write_fast_pdf(pdf_path, _sample_metadata(), "")
            self.assertTrue(pdf_path.exists())
            self.assertGreater(pdf_path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
