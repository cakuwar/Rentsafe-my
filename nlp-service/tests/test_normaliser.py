"""Unit tests for the Shortform Normaliser (FYP1 target: 50 input-output pairs).

Covers: negation expansion, reduplication digits, multi-word phrases,
passthrough of unknown tokens (e.g. place names). Every pair here is
verified directly against SHORTFORM_DICT / DIGIT_RULES (loaded from the
project's CSVs) rather than hand-guessed, so a pair only fails if the
underlying data or normalise() logic actually regresses.
"""
import pytest
from app.normaliser.normaliser import normalise

# -- plain shortform expansion (single token, curated dictionary entry) -----
PLAIN_SHORTFORM_PAIRS = [
    ("byr", "bayar"),
    ("tgk", "tengok"),
    ("sy", "saya"),
    ("dh", "dah"),
    ("blh", "boleh"),
    ("dpt", "dapat"),
    ("utk", "untuk"),
    ("dgn", "dengan"),
    ("skrg", "sekarang"),
    ("nk", "nak"),
    ("mcm", "macam"),
    ("tp", "tapi"),
    ("tu", "itu"),
    ("ni", "ini"),
    ("sbb", "sebab"),
    ("bg", "bagi"),
    ("tlg", "tolong"),
    ("kt", "kat"),
    ("kat", "di"),
    ("dr", "dari"),
    ("byk", "banyak"),
    ("skit", "sikit"),
    ("brg", "barang"),
    ("org", "orang"),
    ("buleh", "boleh"),
]

# -- negation expansion: "x" prefix -> "tak" ---------------------------------
NEGATION_PAIRS = [
    ("xleh", "tak boleh"),
    ("xnak", "tak nak"),
    ("xpe", "tak apa"),
    ("xmau", "tak mahu"),
    ("xkan", "tak akan"),
    ("xkn", "tak akan"),
]

# -- reduplication: trailing "2" digit and ditto-mark ------------------------
REDUPLICATION_PAIRS = [
    ("kawan2", "kawan-kawan"),
    ("elok2", "elok-elok"),
    ("brg2", "barang-barang"),      # base expanded (brg -> barang) then reduplicated
    ("org2", "orang-orang"),        # base expanded (org -> orang) then reduplicated
    ("buleh2", "boleh-boleh"),
    ("skit2", "sikit-sikit"),
    ('tiba""tiba', "tiba-tiba"),    # ditto-mark reduplication
    ('Lain""la', "lain-lain la"),
]

# -- digit leetspeak: whole-token phonetic substitution ----------------------
LEETSPEAK_PAIRS = [
    ("gr8", "great"),
    ("w8", "wait"),
    ("l8r", "later"),
    ("sk8", "skate"),
    ("2u", "to you"),
    ("2nite", "tonight"),
    ("2day", "today"),
    ("wt4u", "waiting for you"),
    ("gift4u", "gift for you"),
    ("b4", "before"),
]

# -- multi-word phrases: several rules combined in one sentence -------------
PHRASE_PAIRS = [
    ("byr deposit", "bayar deposit"),
    ("sy dh byr deposit", "saya dah bayar deposit"),
    ("xleh tgk bilik", "tak boleh tengok bilik"),
    ("blh tlg", "boleh tolong"),
    ("nk sewa bilik dgn org lain", "nak sewa bilik dengan orang lain"),
    ("sy dh byr deposit bulan ni", "saya dah bayar deposit bulan ini"),
]

# -- passthrough: unknown tokens (place names, numbers, ambiguous entries) --
PASSTHROUGH_PAIRS = [
    ("cheras", "cheras"),
    ("kl", "kl"),
    ("condo", "condo"),
    ("unit", "unit"),
    ("wifi", "wifi"),
    ("chat", "chat"),           # explicitly marked ambiguous in the CSV
    ("rm2500", "rm2500"),       # price, not reduplication
    ("rm2", "rm2"),             # currency amount, not "rm-rm"
    ("no2", "no2"),             # not a Malay word to reduplicate
    ("2", "2"),                 # standalone "2" is ambiguous, not auto-applied
    ("3", "3"),                 # standalone "3" is LOW-confidence, not auto-applied
]

ALL_PAIRS = (
    PLAIN_SHORTFORM_PAIRS
    + NEGATION_PAIRS
    + REDUPLICATION_PAIRS
    + LEETSPEAK_PAIRS
    + PHRASE_PAIRS
    + PASSTHROUGH_PAIRS
)


def test_pair_bank_meets_fyp1_target():
    assert len(ALL_PAIRS) >= 50


@pytest.mark.parametrize(("input_text", "expected_output"), ALL_PAIRS)
def test_normaliser(input_text, expected_output):
    assert normalise(input_text) == expected_output


# ---------------------------------------------------------------------------
# English homographs
#
# The shortform dictionary is sourced from Malay SMS glossaries, where "come"
# abbreviates "comel" (cute) and "no" abbreviates "nombor". RentSafe's
# conversations are code-switched, so those entries rewrote ordinary English:
# "come by on Saturday" became "comel by on saturday", and "no viewing allowed"
# became "nombor viewing allowed" — which destroyed layer 1's viewing_denial
# flag outright.
#
# Both are now marked ambiguous in the CSV, which the loader already excludes
# from automatic replacement. eval/slang_map_audit.py re-checks the whole map.
# ---------------------------------------------------------------------------

def test_english_come_is_not_rewritten_to_comel():
    assert "comel" not in normalise("Sure, come by on Saturday")
    assert "come" in normalise("Sure, come by on Saturday")


def test_english_no_is_not_rewritten_to_nombor():
    assert "nombor" not in normalise("no viewing allowed for this unit")


def test_no_viewing_survives_normalisation():
    """The concrete regression: a red flag was being erased by the normaliser."""
    from app.layer1.red_flags import extract_red_flags

    assert "viewing_denial" in extract_red_flags(
        normalise("Owner: no viewing allowed for this unit")
    )


def test_meaning_preserving_loanwords_still_normalise():
    """Only homographs were demoted; real translations stay active."""
    assert "pemilik" in normalise("Owner: hello")
    assert "tempah" in normalise("can I book the room")


def test_slang_map_has_no_unaudited_english_homographs():
    """Fails if a future dictionary update reintroduces one."""
    from app.normaliser.dictionary import _load_shortform_dict

    active = _load_shortform_dict()
    # Words whose Malay expansion means something different from the English.
    for word in ("come", "no", "chat"):
        assert word not in active, (
            f"'{word}' maps to '{active.get(word)}' and would corrupt English text"
        )


# --- links are never expanded ------------------------------------------------

@pytest.mark.parametrize("text", [
    "go.ibilik.com",
    "Go to: go.ibilik.com. Login",
    "https://go.ibilik.com/sign?x=1",
    "visit www.mudah.my/rent now",
    "link: bit.ly/kaki2 tq",
    "email owner@gmail.com tq",
    "www.rumah2.com.my",
])
def test_link_tokens_are_left_exactly_as_written(text):
    from app.normaliser.normaliser import _LINK_TOKEN, normalise

    links = [t for t in text.lower().split() if _LINK_TOKEN.match(t)]
    assert links, "fixture must contain a link"
    out = normalise(text).split()
    for link in links:
        assert link in out


@pytest.mark.parametrize("text, kept", [
    ("Goto: cm login using your number", "cm"),        # the real iBilik case
    ("go to: cm complete the signing", "cm"),
    ("link: dgn", "dgn"),
])
def test_the_token_after_a_link_cue_is_not_treated_as_slang(text, kept):
    from app.normaliser.normaliser import normalise

    assert kept in normalise(text).split()


def test_the_same_slang_is_still_expanded_elsewhere():
    """The dictionary entry is right in general; only the link position is exempt."""
    from app.normaliser.normaliser import normalise

    assert normalise("cm tu la") == "macam itu la"
    assert normalise("datang dgn kawan") == "datang dengan kawan"
