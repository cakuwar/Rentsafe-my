"""Shortform Normaliser dictionary (FYP1 — P3).

Maps Malaysian WhatsApp-register abbreviations (Manglish) to standard forms.
Target for FYP1 is a ~200-entry dictionary. Build it up as you inspect the
collected scam/legit dataset — this is genuine dataset-driven work, not
something to guess up front.

Rule of thumb: abbreviation expansion MUST run before any downstream
classification, otherwise out-of-vocabulary shortforms just get dropped/
mis-embedded by the tokenizer.
"""

import csv
from dataclasses import dataclass, field
from pathlib import Path


_CSV_PATH = Path(__file__).with_name("rentsafe_manglish_shortform_dictionary_v2.csv")
_DIGIT_CSV_PATH = Path(__file__).with_name("rentsafe_digit_substitution_rules.csv")


def _load_shortform_dict() -> dict[str, str]:
    """Load verified CSV entries into the lookup dictionary.

    Ambiguous entries and explanatory rule rows need context-aware handling,
    so they are kept in the CSV but excluded from automatic replacement.
    """
    with _CSV_PATH.open("r", encoding="utf-8-sig", newline="") as csv_file:
        rows = csv.DictReader(csv_file)
        return {
            row["short_form"].strip().lower(): row["normalised_form"].strip()
            for row in rows
            if row.get("ambiguous", "").strip().upper() == "N"
            and row.get("short_form", "").strip()
            and row.get("normalised_form", "").strip()
            and not row["short_form"].strip().startswith("[")
        }


@dataclass
class DigitRules:
    """Digit-substitution rules, bucketed by how normaliser.py applies them."""

    prefixes: dict[str, str] = field(default_factory=dict)
    reduplication_suffixes: set[str] = field(default_factory=set)
    ditto_markers: list[str] = field(default_factory=list)
    leet_tokens: dict[str, str] = field(default_factory=dict)


def _load_digit_rules() -> DigitRules:
    """Load rentsafe_digit_substitution_rules.csv into applyable rule buckets.

    Rows marked category=AMBIGUOUS or confidence=LOW/LOW-UNVERIFIED are
    skipped entirely — e.g. standalone "2" -> "itu" and standalone "3" ->
    "tiga" — per the CSV's own notes, these conflict with the far
    better-attested reduplication reading and must not be auto-applied.

    MEDIUM-confidence phonetic rows (leetspeak like "gr8", "2nite", "wt4u")
    are loaded as exact whole-token lookups rather than generic per-digit
    substitution. Rental listings are full of prices and phone numbers, so
    blindly swapping a digit for a word wherever it appears would corrupt
    that numeric content.
    """
    rules = DigitRules()
    with _DIGIT_CSV_PATH.open("r", encoding="utf-8-sig", newline="") as csv_file:
        for row in csv.DictReader(csv_file):
            category = row.get("category", "").strip().upper()
            confidence = row.get("confidence", "").strip().upper()
            if category == "AMBIGUOUS" or confidence.startswith("LOW"):
                continue

            pattern = row.get("pattern", "").strip()
            rule_type = row.get("rule_type", "").strip().lower()

            if "prefix" in rule_type:
                # e.g. "tak / tidak" -> "tak" (the dominant colloquial choice)
                rules.prefixes[pattern] = row["substitution"].split("/")[0].strip()
            elif "reduplication marker" in rule_type:
                # pattern is e.g. '"" (ditto mark, trailing)' - keep just the marker
                rules.ditto_markers.append(pattern.split(" ", 1)[0])
            elif "suffix" in rule_type and category == "REDUPLICATION":
                rules.reduplication_suffixes.add(pattern)
            elif "phonetic" in rule_type or "whole-token" in rule_type:
                inputs = [tok.strip().lower() for tok in row["example_input"].split(",")]
                outputs = [tok.strip() for tok in row["example_expanded"].split(",")]
                for token_in, token_out in zip(inputs, outputs):
                    if token_in and token_out:
                        rules.leet_tokens[token_in] = token_out
    return rules


SHORTFORM_DICT: dict[str, str] = _load_shortform_dict()
DIGIT_RULES: DigitRules = _load_digit_rules()
