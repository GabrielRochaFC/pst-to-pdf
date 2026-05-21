"""Synthetic tests for validator behavior with status=filtered rows.

Uses temp dirs with empty .eml/.pdf placeholders and a hand-rolled manifest CSV.
No real PST data.
"""

import csv
import tempfile
import unittest
from pathlib import Path

from pst_to_pdf.converter import MANIFEST_FIELDS


def _write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({f: row.get(f, "") for f in MANIFEST_FIELDS})


class TestValidatorFilteredRows(unittest.TestCase):
    def test_filtered_rows_counted_and_do_not_fail_validation(self):
        from pst_to_pdf.validator import validate_output

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eml_dir = root / "eml"
            pdf_dir = root / "pdf"
            manifest = root / "manifest" / "case.csv"
            eml_dir.mkdir(parents=True)
            pdf_dir.mkdir(parents=True)

            eml_ok = eml_dir / "1.eml"
            eml_filt = eml_dir / "2.eml"
            pdf_ok = pdf_dir / "1.pdf"
            eml_ok.write_text("", encoding="utf-8")
            eml_filt.write_text("", encoding="utf-8")
            pdf_ok.write_text("%PDF-1.4\n%%EOF\n", encoding="utf-8")

            _write_manifest(manifest, [
                {"eml_path": str(eml_ok), "pdf_path": str(pdf_ok), "status": "ok"},
                {"eml_path": str(eml_filt), "pdf_path": "", "status": "filtered",
                 "error": "filtered by email participant"},
            ])

            summary = validate_output(eml_dir, pdf_dir, manifest)
            self.assertEqual(summary.filtered_rows, 1)
            self.assertEqual(summary.successful_rows, 1)
            self.assertEqual(summary.missing_pdfs_for_successful_rows, 0)
            self.assertEqual(summary.eml_files_missing_manifest_rows, 0)
            self.assertFalse(summary.has_consistency_errors())


if __name__ == "__main__":
    unittest.main()
