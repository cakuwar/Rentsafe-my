import pytest

from app.normaliser.normaliser import normalise
from app.normaliser.dictionary import SHORTFORM_DICT, DIGIT_RULES

@pytest.mark.parametrize(
     ("input_text", "expected_output"),
    [
        ("byr", "bayar"),
        ("tgk", "tengok"),
        ("sy", "saya"),
        ("dh", "dah"),
        ("byr deposit", "bayar deposit"),
        ("sy dh byr deposit", "saya dah bayar deposit"),
        ("  BYR   deposit  ", "bayar deposit"),
        ("Cheras condo", "cheras condo"),
        ("xleh tgk", "tak boleh tengok"),
    ],
)
def test_normalise_input_output(input_text, expected_output):
    assert normalise(input_text) == expected_output


def test_dictionary_loaded_from_csv():
    assert len(SHORTFORM_DICT) > 500
    assert SHORTFORM_DICT["byr"] == "bayar"


def test_ambiguous_entry_is_not_normalised():
    assert normalise("chat") == "chat"


def test_empty_input():
    with pytest.raises(ValueError):
        normalise("")


# --- digit substitution: prefix negation (x -> tak) --------------------

@pytest.mark.parametrize(
    ("input_text", "expected_output"),
    [
        ("xnak", "tak nak"),          # curated dictionary entry (multi-word)
        ("xleh", "tak boleh"),        # curated entry wins over generic x+leh
        ("xpe", "tak apa"),
        ("xmau", "tak mahu"),
    ],
)
def test_negation_prefix_expansion(input_text, expected_output):
    assert normalise(input_text) == expected_output


# --- digit substitution: trailing "2" reduplication ---------------------

@pytest.mark.parametrize(
    ("input_text", "expected_output"),
    [
        ("kawan2", "kawan-kawan"),   # base word already standard
        ("elok2", "elok-elok"),
        ("brg2", "barang-barang"),   # base is itself a shortform (brg -> barang)
        ("org2", "orang-orang"),     # base is itself a shortform (org -> orang)
    ],
)
def test_reduplication_suffix_expansion(input_text, expected_output):
    assert normalise(input_text) == expected_output


def test_reduplication_suffix_skips_currency_and_non_malay_bases():
    """"rm2"/"no2" are currency/number tokens, not Malay words to reduplicate."""
    assert normalise("rm2 deposit") == "rm2 deposit"
    assert normalise("rm2500 sebulan") == "rm2500 sebulan"
    assert normalise("no2") == "no2"


def test_standalone_ambiguous_digits_are_not_touched():
    """Standalone "2" ("itu") and "3" ("tiga") are LOW-confidence/ambiguous
    per the CSV notes, so they must pass through unexpanded."""
    assert normalise("2") == "2"
    assert normalise("3") == "3"


# --- digit substitution: ditto-mark reduplication ------------------------

@pytest.mark.parametrize(
    ("input_text", "expected_output"),
    [
        ('tiba""tiba', "tiba-tiba"),
        ('Lain""la', "lain-lain la"),
    ],
)
def test_ditto_mark_reduplication(input_text, expected_output):
    assert normalise(input_text) == expected_output


# --- digit substitution: whole-token leetspeak ---------------------------

@pytest.mark.parametrize(
    ("input_text", "expected_output"),
    [
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
    ],
)
def test_leetspeak_whole_token_expansion(input_text, expected_output):
    assert normalise(input_text) == expected_output


def test_digit_rules_loaded_from_csv():
    assert DIGIT_RULES.prefixes == {"x": "tak"}
    assert DIGIT_RULES.reduplication_suffixes == {"2"}
    assert DIGIT_RULES.ditto_markers == ['""']
    assert DIGIT_RULES.leet_tokens["gr8"] == "great"


# --- punctuation is preserved around an expanded token -------------------

@pytest.mark.parametrize(
    ("input_text", "expected_output"),
    [
        ("xleh?", "tak boleh?"),
        ("(nego)", "(nego)"),
        ('"xleh"', '"tak boleh"'),
        ("xleh, tgk.", "tak boleh, tengok."),
        ("call skrg!!", "call sekarang!!"),
    ],
)
def test_punctuation_preserved_around_expansion(input_text, expected_output):
    assert normalise(input_text) == expected_output


def test_token_with_internal_punctuation_is_left_untouched():
    """A hyphenated phone number or a contraction can't be safely split into
    a single word core, so it must pass through unchanged rather than being
    mangled."""
    assert normalise("call012-3456789") == "call012-3456789"
    assert normalise("can't") == "can't"