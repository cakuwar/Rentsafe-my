"""Minimal pairs: one pair per pair_id, and a test split that cannot be memorised.

The first version held out whole pairs but built every pair from the same
sentence banks, so 92 of the 93 mechanic sentences in the test split also
appeared in training and pair accuracy rewarded recognising them. Test pairs now
come from a held-out family of phrasings.
"""
import os
import re

import pandas as pd
import pytest

from training import make_minimal_pairs as mmp

AUGMENTED = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "processed", "augmented")
MECHANIC_BANKS = ["legit_viewing", "scam_viewing", "legit_payment", "scam_payment",
                  "legit_keys", "legit_agreement", "scam_extra"]
AMOUNT = re.compile(r"\brm\s?\d", re.I)


@pytest.fixture(scope="module")
def generated():
    return mmp.generate(pairs=80, seed=3, test_share=0.25)


def _answers(bank):
    for options in bank.values():
        for option in options:
            yield option[1] if isinstance(option, tuple) else option


def test_heldout_family_shares_no_mechanic_sentence_with_train():
    for name in MECHANIC_BANKS:
        train = set(_answers(mmp.FAMILIES["train"][name]))
        heldout = set(_answers(mmp.FAMILIES["heldout"][name]))
        assert not train & heldout, f"{name}: {train & heldout}"


def _check_rows(rows):
    by_pair = {}
    for row in rows:
        if row["kind"] not in mmp.TWIN_KINDS:
            continue
        by_pair.setdefault(row["pair_id"], []).append(row)
    for pair, members in by_pair.items():
        labels = sorted(row["label"] for row in members)
        assert labels == ["LEGITIMATE", "SCAM"], f"{pair}: {labels}"
        legit, scam = (next(r["text"] for r in members if r["label"] == label)
                       for label in ("LEGITIMATE", "SCAM"))
        a, b = legit.split("\n"), scam.split("\n")
        assert len(a) == len(b), f"{pair}: twins differ in length"
        for x, y in zip(a, b):
            if x.startswith("Renter:") or y.startswith("Renter:"):
                assert x == y, f"{pair}: twins ask different questions"
        assert len(AMOUNT.findall(legit)) == len(AMOUNT.findall(scam)), \
            f"{pair}: twins name different numbers of amounts"


def test_each_pair_id_is_one_legit_and_one_scam_twin(generated):
    train, test = generated
    _check_rows(train)
    _check_rows(test)


def test_families_and_groups(generated):
    train, test = generated
    assert {row["family"] for row in train} == {"train"}
    assert {row["family"] for row in test} == {"heldout"}
    assert not {r["source_group"] for r in train} & {r["source_group"] for r in test}
    # Derived rows have their own pair_id but their parent's source_group.
    suffix = {"full": "", "fragment": "-F", "truncated": "-T", "prefix": "-P", "core": "-C"}
    for row in train + test:
        assert row["pair_id"] == row["source_group"] + suffix[row["kind"]]


def test_no_test_mechanic_sentence_appears_in_training(generated):
    train, test = generated
    stats = mmp.verify(train, test)
    assert stats["test_mechanic_lines"] > 0 and stats["seen_in_train"] == 0


def test_verify_rejects_a_leaked_sentence(generated):
    """The guard must bite: plant one test mechanic sentence in training."""
    train, test = generated
    leaked = sorted(mmp.mechanic_lines(test))[0]
    planted = [dict(train[0], text=train[0]["text"] + "\nOwner: " + leaked)] + train[1:]
    with pytest.raises(AssertionError, match="also in training"):
        mmp.verify(planted, test)


def test_the_files_on_disk_hold_the_same_guarantees():
    paths = [os.path.join(AUGMENTED, f"minimal_pairs_{split}.csv") for split in ("train", "test")]
    if not all(os.path.exists(path) for path in paths):
        pytest.skip("generated pairs not present (data/processed is gitignored)")
    train, test = (pd.read_csv(path).to_dict("records") for path in paths)
    assert {"pair_id", "family"} <= set(train[0]), "old files - rerun make_minimal_pairs.py"
    _check_rows(train)
    _check_rows(test)
    mmp.verify(train, test)


def _messages(text):
    """Messages, not text lines: a price breakdown is one message over several lines."""
    return len(re.findall(r"^(?:Renter|Owner): ", text, re.M))


def test_prefixes_hold_no_scam_behaviour_and_cores_do(generated):
    """A prefix is text both twins share, labelled LEGITIMATE; its core is as
    many lines of the scam twin, including a scam line, labelled SCAM."""
    train, test = generated
    for rows in (train, test):
        full = {}
        for row in rows:
            if row["kind"] == "full":
                full.setdefault(row["source_group"], {})[row["label"]] = set(row["text"].split("\n"))
        prefixes = {r["source_group"]: r for r in rows if r["kind"] == "prefix"}
        cores = {r["source_group"]: r for r in rows if r["kind"] == "core"}
        assert prefixes and set(prefixes) == set(cores)
        for group, prefix in prefixes.items():
            twins = full[group]
            lines = prefix["text"].split("\n")
            assert prefix["label"] == "LEGITIMATE"
            assert all(l in twins["LEGITIMATE"] and l in twins["SCAM"] for l in lines)
            core = cores[group]["text"].split("\n")
            assert cores[group]["label"] == "SCAM"
            assert _messages(cores[group]["text"]) == _messages(prefix["text"])
            assert any(l not in twins["LEGITIMATE"] for l in core)


def test_derived_rows_do_not_make_length_a_shortcut(generated):
    """Prefixes are short and all LEGITIMATE; cores must match them in length."""
    train, _ = generated
    by_label = {"LEGITIMATE": [], "SCAM": []}
    for row in train:
        if row["kind"] in ("prefix", "core"):
            by_label[row["label"]].append(_messages(row["text"]))
    assert sorted(by_label["LEGITIMATE"]) == sorted(by_label["SCAM"])
