"""Guards on the sealed held-out test set.

data/test_real/ is the only evaluation data in the project that can say anything
about real-world performance, and it is worth exactly as much as its isolation.
These tests fail the build if that isolation breaks — if a held-out conversation
turns up in training, or if a notebook or script starts reading the folder.

They pass on an empty folder: the set is expected to be empty until real
conversations are collected.
"""
import glob
import os

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEST_DIR = os.path.join(ROOT, "data", "test_real")
PROCESSED = os.path.join(ROOT, "data", "processed")
NLP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _normalise(text):
    return " ".join(str(text).split()).lower()


def held_out_frames():
    paths = sorted(glob.glob(os.path.join(TEST_DIR, "*.csv")))
    if not paths:
        return None
    return pd.concat([pd.read_csv(path) for path in paths], ignore_index=True)


def training_texts():
    texts = set()
    for path in glob.glob(os.path.join(PROCESSED, "*", "*.csv")):
        frame = pd.read_csv(path)
        if "text" in frame.columns:
            texts.update(_normalise(text) for text in frame["text"])
    return texts


# --- the folder itself -----------------------------------------------------

def test_held_out_folder_exists():
    assert os.path.isdir(TEST_DIR), "data/test_real/ is missing"


def test_held_out_has_a_readme_explaining_the_rule():
    readme = os.path.join(TEST_DIR, "README.md")
    assert os.path.exists(readme)
    text = open(readme, encoding="utf-8").read().lower()
    assert "never" in text and "train" in text


# --- isolation -------------------------------------------------------------

def test_no_held_out_row_appears_in_train_or_val():
    """The one rule that makes this set worth anything."""
    frame = held_out_frames()
    if frame is None:
        pytest.skip("data/test_real/ is empty, which is the expected start state")

    seen = training_texts()
    overlaps = [
        index for index, text in enumerate(frame["text"])
        if _normalise(text) in seen
    ]
    assert not overlaps, (
        f"rows {overlaps} also appear in data/processed — they are not held out"
    )


def test_held_out_rows_are_real_not_synthetic():
    frame = held_out_frames()
    if frame is None:
        pytest.skip("data/test_real/ is empty")
    if "origin" in frame.columns:
        assert set(frame["origin"].str.lower()) <= {"real"}


def test_held_out_labels_are_valid():
    frame = held_out_frames()
    if frame is None:
        pytest.skip("data/test_real/ is empty")
    labels = set(frame["label"].str.upper().replace({"LEGIT": "LEGITIMATE"}))
    assert labels <= {"SCAM", "LEGITIMATE"}


# --- nothing may train on it -----------------------------------------------

def _code_of(path):
    """The executable part of a file.

    For a notebook that is the code cells only: markdown that says "do not
    upload data/test_real/" is the documentation protecting the set, and an
    earlier version of this test flagged it as a violation.
    """
    import json

    if path.endswith(".ipynb"):
        notebook = json.load(open(path, encoding="utf-8"))
        return "\n".join(
            "".join(cell["source"])
            for cell in notebook["cells"]
            if cell["cell_type"] == "code"
        )
    return open(path, encoding="utf-8", errors="ignore").read()


def test_no_training_code_reads_the_held_out_folder():
    """Notebooks and training scripts must not touch data/test_real/.

    training/audit_training_data.py is deliberately not scanned: it reads the
    sealed set for the opposite reason — to prove no augmented row overlaps it.
    """
    offenders = []
    patterns = [
        os.path.join(NLP, "*.ipynb"),
        os.path.join(NLP, "*.py"),
        os.path.join(NLP, "app", "**", "*.py"),
    ]
    for pattern in patterns:
        for path in glob.glob(pattern, recursive=True):
            if "test_real" in _code_of(path):
                offenders.append(os.path.relpath(path, NLP))

    assert not offenders, (
        f"these read the sealed test set: {offenders}. Only eval/ may."
    )


def test_the_code_check_still_catches_a_real_read(tmp_path):
    """Narrowing the check to code cells must not blind it."""
    import json

    offending = tmp_path / "bad.ipynb"
    offending.write_text(json.dumps({"cells": [
        {"cell_type": "markdown", "source": ["harmless mention of test_real\n"]},
        {"cell_type": "code", "source": ["pd.read_csv('data/test_real/x.csv')\n"]},
    ]}), encoding="utf-8")
    harmless = tmp_path / "ok.ipynb"
    harmless.write_text(json.dumps({"cells": [
        {"cell_type": "markdown", "source": ["do not upload data/test_real/\n"]},
        {"cell_type": "code", "source": ["print('hello')\n"]},
    ]}), encoding="utf-8")

    assert "test_real" in _code_of(str(offending))
    assert "test_real" not in _code_of(str(harmless))
