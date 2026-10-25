"""Personal data from the real screenshots must not reach tracked files.

The names themselves are only in data/samples/redact.txt (gitignored), so the
repo-wide check skips on a machine that does not have the screenshots.
"""
import os

import pytest

from training import redaction

NLP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(NLP)

# Folders that are tracked and could plausibly pick up a pasted name.
TRACKED = [
    os.path.join(NLP, "app"),
    os.path.join(NLP, "training"),
    os.path.join(NLP, "tests"),
    os.path.join(NLP, "eval"),
    os.path.join(ROOT, "docs"),
    os.path.join(ROOT, "backend", "src"),
]
# Gitignored, per the root .gitignore: raw outputs that are allowed to hold it.
IGNORED = [
    os.path.join(NLP, "eval", "results", "blind_legit"),
]
TEXT = (".py", ".js", ".md", ".json", ".txt", ".csv", ".ipynb")


@pytest.fixture
def private_list(tmp_path, monkeypatch):
    path = tmp_path / "redact.txt"
    path.write_text("# comment\nJane Q Public\nJane\n[address] 1 Jalan Contoh 3/4\n",
                    encoding="utf-8")
    monkeypatch.setattr(redaction, "LIST", str(path))
    return path


def test_names_are_replaced_longest_first(private_list):
    assert redaction.redact("Hi, Jane Q Public here") == "Hi, [name] here"
    assert redaction.redact("jane said") == "[name] said"


def test_names_glued_by_ocr_are_still_caught(private_list):
    assert redaction.redact("En JaneRumahSewa") == "En [name]RumahSewa"


def test_tagged_entries_use_their_tag(private_list):
    assert redaction.redact("Owner: 1 JALAN CONTOH 3/4") == "Owner: [address]"


@pytest.mark.parametrize("number", [
    "+60 12-345 6789", "012-345 6789", "0123456789", "990101-14-5678",
    "1234 5678 9012",
])
def test_phone_ic_and_account_numbers_are_replaced(number):
    assert redaction.redact(f"call {number} now") == "call [phone] now"
    assert redaction.leaks(number) == ["[phone-like number]"]


@pytest.mark.parametrize("text", [
    "Limited Time Only! 10 Aug 2026 - 31 Aug 2026",
    "Total Move-in: RM 1300", "RM 1,300.00", "on 20/8 at 11.45am",
])
def test_dates_and_money_are_left_alone(text):
    """The first pattern redacted "2026 - 31" as a phone number."""
    assert redaction.redact(text) == text


def test_no_listed_name_in_any_tracked_file():
    names = redaction.names()
    if not names:
        pytest.skip("data/samples/redact.txt not present")
    hits = []
    for top in TRACKED:
        for folder, _, files in os.walk(top):
            if any(folder.startswith(ignored) for ignored in IGNORED):
                continue
            for name in files:
                path = os.path.join(folder, name)
                if not name.endswith(TEXT) or path in IGNORED:
                    continue
                with open(path, encoding="utf-8", errors="ignore") as handle:
                    found = [n for n in redaction.leaks(handle.read())
                             if n in names]
                if found:
                    hits.append(os.path.relpath(path, ROOT))
    assert hits == [], f"personal data in tracked files: {hits}"
