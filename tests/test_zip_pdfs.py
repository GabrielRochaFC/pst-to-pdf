"""Synthetic tests for the zip-pdfs utility.

Uses temp dirs with placeholder .pdf files. No real PST/PDF content.
"""

import tempfile
import unittest
import zipfile
from pathlib import Path

from pst_to_pdf.zip_pdfs import discover_pdf_folders, list_pdf_files, run, zip_folder


def _make_pdf_folder(root: Path, slug: str, n_pdfs: int) -> Path:
    pdf_dir = root / "output" / slug / "pdf"
    pdf_dir.mkdir(parents=True)
    for i in range(n_pdfs):
        (pdf_dir / f"{i:02d}_email.pdf").write_text("%PDF-1.4\n%%EOF\n", encoding="utf-8")
    return pdf_dir


class TestDiscoverPdfFolders(unittest.TestCase):
    def test_finds_only_slugs_with_pdf_subdir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_pdf_folder(root, "user-002", 2)
            _make_pdf_folder(root, "user-001", 1)
            (root / "output" / "user-003" / "eml").mkdir(parents=True)  # no pdf/

            folders = discover_pdf_folders(root)
            self.assertEqual([slug for slug, _ in folders], ["user-001", "user-002"])

    def test_missing_output_dir_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(discover_pdf_folders(Path(tmp)), [])


class TestListPdfFiles(unittest.TestCase):
    def test_only_pdf_files_flat(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_dir = Path(tmp)
            (pdf_dir / "a.pdf").write_text("x", encoding="utf-8")
            (pdf_dir / "b.PDF").write_text("x", encoding="utf-8")
            (pdf_dir / "notes.txt").write_text("x", encoding="utf-8")
            (pdf_dir / "subdir").mkdir()

            files = list_pdf_files(pdf_dir)
            self.assertEqual([p.name for p in files], ["a.pdf", "b.PDF"])


class TestZipFolder(unittest.TestCase):
    def test_creates_zip_with_flat_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_dir = _make_pdf_folder(root, "user-001", 3)
            zip_path = root / "zipped" / "user-001-pdfs.zip"
            zip_path.parent.mkdir(parents=True)

            result = zip_folder("user-001", pdf_dir, zip_path)

            self.assertEqual(result.status, "ok")
            self.assertEqual(result.pdf_count, 3)
            self.assertTrue(zip_path.is_file())
            with zipfile.ZipFile(zip_path) as zf:
                self.assertEqual(sorted(zf.namelist()), ["00_email.pdf", "01_email.pdf", "02_email.pdf"])

    def test_empty_folder_is_skipped_and_no_zip_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_dir = _make_pdf_folder(root, "user-empty", 0)
            zip_path = root / "zipped" / "user-empty-pdfs.zip"
            zip_path.parent.mkdir(parents=True)

            result = zip_folder("user-empty", pdf_dir, zip_path)

            self.assertEqual(result.status, "skipped")
            self.assertFalse(zip_path.exists())

    def test_overwrites_existing_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_dir = _make_pdf_folder(root, "user-001", 1)
            zip_path = root / "zipped" / "user-001-pdfs.zip"
            zip_path.parent.mkdir(parents=True)
            zip_path.write_text("stale", encoding="utf-8")

            result = zip_folder("user-001", pdf_dir, zip_path)

            self.assertEqual(result.status, "ok")
            with zipfile.ZipFile(zip_path) as zf:
                self.assertEqual(zf.namelist(), ["00_email.pdf"])


class TestRun(unittest.TestCase):
    def test_missing_case_dir_returns_friendly_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does-not-exist"
            self.assertEqual(run(missing), 2)

    def test_missing_output_dir_returns_friendly_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run(Path(tmp)), 2)

    def test_no_pdf_folders_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "output").mkdir()
            self.assertEqual(run(root), 0)

    def test_full_run_creates_zips_and_skips_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_pdf_folder(root, "user-001", 2)
            _make_pdf_folder(root, "user-002", 0)

            code = run(root)

            self.assertEqual(code, 0)
            zipped_dir = root / "zipped"
            self.assertTrue((zipped_dir / "user-001-pdfs.zip").is_file())
            self.assertFalse((zipped_dir / "user-002-pdfs.zip").exists())

    def test_dry_run_creates_no_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_pdf_folder(root, "user-001", 2)

            code = run(root, dry_run=True)

            self.assertEqual(code, 0)
            self.assertFalse((root / "zipped").exists())


if __name__ == "__main__":
    unittest.main()
