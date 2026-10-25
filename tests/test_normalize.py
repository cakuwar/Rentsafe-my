"""Tests for scripts/scrapers/normalize.py.

Run with: python -m pytest tests/test_normalize.py

The scraper implementation (scripts/scrapers/) is kept intact — write your
own tests against it here. Things worth covering, based on what the scraper
needs to guarantee:
  - normalize_area: canonical KL/Selangor area list, case-insensitivity,
    alias mapping (e.g. "PJ" -> "Petaling Jaya"), unknown areas kept but
    flagged for review, None/empty handling
  - normalize_property_type: studio/condo/apartment/landed/room keyword
    matching across multiple text fields, no-match -> None
  - is_price_valid: sane MYR rental bounds
  - normalize_bedrooms: studio -> 0 bedrooms + is_studio flag, numeric
    strings, missing values
  - normalize_row: end-to-end row filtering (drops bad price / wrong state,
    infers property_type from title when missing, flags unknown areas)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.scrapers import config
from scripts.scrapers.normalize import (
    normalize_area,
    normalize_bedrooms,
    normalize_property_type,
    normalize_row,
    is_price_valid,
)

# TODO: write your own test cases (see module docstring above for coverage ideas).


if __name__ == "__main__":
    unittest.main()
