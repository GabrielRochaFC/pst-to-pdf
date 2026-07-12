#!/usr/bin/env python3
"""Compatibility wrapper for pst_to_pdf.zip_pdfs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pst_to_pdf.zip_pdfs import main


if __name__ == "__main__":
    raise SystemExit(main())
