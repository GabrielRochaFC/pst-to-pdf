"""Synthetic tests for converter's filtered-row helper and filter-check helper.

No real PST data. Builds manifest rows in memory and synthetic EML files in
tempdirs.
"""

import csv
import io
import tempfile
import unittest
from pathlib import Path

from pst_to_pdf.converter import MANIFEST_FIELDS, filtered_row


class TestFilteredRow(unittest.TestCase):
    def test_shape(self):
        row = filtered_row(
            source_pst=Path("/tmp/case/input/x.pst"),
            pst_sha256="deadbeef",
            eml_path=Path("/tmp/case/output/x/eml/1.eml"),
            metadata={
                "Subject":     "Hello",
                "From":        "a@x.com",
                "To":          "b@y.com",
                "Cc":          "",
                "Bcc":         "",
                "Date":        "Mon, 1 Jan 2024 00:00:00 +0000",
                "Message-ID":  "<id@host>",
            },
        )
        self.assertEqual(row["status"], "filtered")
        self.assertEqual(row["pdf_path"], "")
        self.assertEqual(row["error"], "filtered by email participant")
        self.assertEqual(row["subject"], "Hello")
        self.assertEqual(row["from"], "a@x.com")
        self.assertEqual(row["to"], "b@y.com")
        self.assertEqual(row["message_id"], "<id@host>")
        self.assertEqual(row["attachment_filenames"], "")
        for field in MANIFEST_FIELDS:
            self.assertIn(field, row)

    def test_csv_round_trip_preserves_status(self):
        row = filtered_row(
            source_pst=Path("/tmp/case/input/x.pst"),
            pst_sha256="deadbeef",
            eml_path=Path("/tmp/case/output/x/eml/2.eml"),
            metadata={
                "Subject": "S", "From": "a@x.com", "To": "", "Cc": "",
                "Bcc": "", "Date": "", "Message-ID": "",
            },
        )
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerow(row)
        buf.seek(0)
        reader = csv.DictReader(buf)
        round_tripped = next(reader)
        self.assertEqual(round_tripped["status"], "filtered")
        self.assertEqual(round_tripped["pdf_path"], "")


from pst_to_pdf.converter import filter_check_eml


def _write_eml(path: Path, headers: dict[str, str]) -> None:
    lines = [f"{k}: {v}" for k, v in headers.items()]
    lines.append("")  # header/body separator
    lines.append("body content — filter must never read this")
    path.write_text("\n".join(lines), encoding="utf-8")


class TestFilterCheckEml(unittest.TestCase):
    def test_match_returns_true_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            eml = Path(tmp) / "1.eml"
            _write_eml(eml, {
                "From": "alice@example.com",
                "To": "bob@x.com",
                "Subject": "Greetings",
            })
            matched, metadata = filter_check_eml(eml, frozenset({"alice@example.com"}))
            self.assertTrue(matched)
            self.assertEqual(metadata["From"], "alice@example.com")
            self.assertEqual(metadata["Subject"], "Greetings")

    def test_no_match_returns_false_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            eml = Path(tmp) / "2.eml"
            _write_eml(eml, {
                "From": "carol@other.com",
                "To": "dan@other.com",
                "Subject": "Unrelated",
            })
            matched, metadata = filter_check_eml(eml, frozenset({"alice@example.com"}))
            self.assertFalse(matched)
            self.assertEqual(metadata["From"], "carol@other.com")
            self.assertEqual(metadata["Subject"], "Unrelated")


if __name__ == "__main__":
    unittest.main()
