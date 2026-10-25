"""Unit tests for Layer 1 red-flag extraction.

Three kinds of test:
  - each flag fires on the phrasing it exists for
  - normal rental language does NOT fire it (these are the ones that matter;
    a flag shown to a renter about an honest landlord is a false accusation)
  - corpus-level rates, so a future pattern edit cannot quietly make the flags
    noisy again
"""
import os

import pandas as pd
import pytest

from app.layer1.red_flags import RED_FLAG_PATTERNS, extract_red_flags
from app.normaliser.normaliser import normalise

DATA = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..", "data", "processed", "random",
)


def flags(text):
    return set(extract_red_flags(text))


# --- each flag fires on what it is for -------------------------------------

@pytest.mark.parametrize("label,text", [
    ("upfront_payment", "kena bayar deposit dulu sebelum viewing"),
    ("upfront_payment", "boleh saja tempah lock 600 dulu"),
    ("upfront_payment", "you need to reserve the unit"),
    ("upfront_payment", "there is a booking fee of RM500"),
    ("pay_before_viewing", "bayar deposit dulu baru boleh viewing"),
    ("pay_before_viewing", "transfer first then we set date time for viewing"),
    ("pay_before_viewing", "after you transfer I will give the key"),
    ("refund_promise", "kalau xjadi dpt balik ye"),
    ("refund_promise", "if takjadi akan refund"),
    ("viewing_denial", "sorry tak boleh view unit ni"),
    ("viewing_denial", "cannot view the unit now"),
    ("remote_owner", "saya outstation di Sabah sekarang"),
    ("remote_owner", "I am overseas at the moment"),
    ("third_party_account", "transfer to the owner company account"),
    ("non_bank_channel", "saya tkda bank sebab itu saya guna tng"),
    ("key_courier", "lepas transfer saya pos kunci"),
    ("key_courier", "I will courier the key to you"),
    ("competition_pressure", "ramai orang tengah tanya unit ni"),
    ("competition_pressure", "many people are asking already"),
    ("personal_details_request", "bagi nama penuh no ic ya"),
    ("proof_of_payment_request", "share me the receipt ya"),
    ("proof_of_payment_request", "hantar resit transfer"),
])
def test_flag_fires(label, text):
    assert label in flags(text), f"{label} did not fire on: {text}"


# --- normal rental language must stay quiet --------------------------------

@pytest.mark.parametrize("text", [
    "Sure, you can come and view the unit this Saturday.",
    "Rent is RM1200 a month, deposit two months.",
    "Deposit akan dipulangkan bila anda keluar nanti.",
    "We sign the tenancy agreement at the office after you view.",
    "Boleh datang tengok rumah hujung minggu ni, saya ada.",
    "Sewa rm900 sebulan, deposit 2 bulan, utiliti rm50.",
    "You can pay the deposit after viewing and signing.",
    "Bila you nak masuk? Saya boleh bukak unit bila-bila.",
])
def test_clean_text_has_no_flags(text):
    assert flags(text) == set(), f"false alarm on: {text}"


def test_refund_at_end_of_tenancy_is_not_a_red_flag():
    """An honest landlord's refundable deposit must not look like a scam.

    Only "refundable if you change your mind about a unit you have not seen"
    is suspicious, which is why the pattern requires the conditional.
    """
    assert "refund_promise" not in flags(
        "deposit akan dipulangkan bila keluar rumah nanti"
    )
    assert "refund_promise" in flags("kalau xjadi nanti dpt balik duit tu")


def test_ordinary_hurry_is_not_urgency_pressure():
    """Real landlords chase tenants too - only competing-interest claims count."""
    assert "competition_pressure" not in flags("cuba confirm awal sikit ya")
    assert "competition_pressure" not in flags("better cepat sikit")
    assert "competition_pressure" not in flags("cuba confirm awal sikit ya")
    assert "competition_pressure" in flags("sebab ada yang tnya juga")


def test_paying_a_deposit_alone_is_not_upfront_payment():
    assert "upfront_payment" not in flags("deposit dua bulan, bayar masa sign")
    assert "upfront_payment" in flags("bayar deposit dulu")


# --- shape of the output ---------------------------------------------------

def test_returns_a_list_of_known_labels():
    result = extract_red_flags("bayar deposit dulu baru boleh view")
    assert isinstance(result, list)
    assert set(result) <= set(RED_FLAG_PATTERNS)


def test_order_is_stable_and_independent_of_the_text():
    """Same flags in the same order regardless of where they appear."""
    first = extract_red_flags("saya outstation. bayar deposit dulu.")
    second = extract_red_flags("bayar deposit dulu. saya outstation.")
    assert first == second


def test_no_duplicate_labels():
    result = extract_red_flags("bayar deposit dulu, kena bayar booking fee dulu")
    assert len(result) == len(set(result))


def test_empty_text_is_safe():
    assert extract_red_flags("") == []


# --- corpus rates, so the patterns cannot silently get noisy ---------------

@pytest.fixture(scope="module")
def corpus():
    paths = [os.path.join(DATA, name) for name in ("train.csv", "val.csv")]
    if not all(os.path.exists(path) for path in paths):
        pytest.skip("labelled corpus not available")
    data = pd.concat([pd.read_csv(path) for path in paths], ignore_index=True)
    data["label"] = data["label"].str.upper().replace({"LEGIT": "LEGITIMATE"})
    data["flags"] = [set(extract_red_flags(normalise(t))) for t in data["text"]]
    return data


def test_most_scams_raise_at_least_one_flag(corpus):
    scam = corpus[corpus["label"] == "SCAM"]
    hit_rate = sum(bool(f) for f in scam["flags"]) / len(scam)
    assert hit_rate >= 0.85, f"only {hit_rate:.1%} of scams flagged"


def test_few_legitimate_conversations_raise_a_flag(corpus):
    legit = corpus[corpus["label"] == "LEGITIMATE"]
    false_alarm = sum(bool(f) for f in legit["flags"]) / len(legit)
    assert false_alarm <= 0.15, f"{false_alarm:.1%} of legitimate flagged"


def test_no_single_flag_is_noisy(corpus):
    """Each flag must be right more often than not when it fires."""
    scam = corpus[corpus["label"] == "SCAM"]
    legit = corpus[corpus["label"] == "LEGITIMATE"]
    for label in RED_FLAG_PATTERNS:
        scam_hits = sum(label in f for f in scam["flags"])
        legit_hits = sum(label in f for f in legit["flags"])
        if scam_hits + legit_hits < 5:
            continue  # too rare in this corpus to judge
        precision = scam_hits / (scam_hits + legit_hits)
        assert precision >= 0.80, f"{label} precision {precision:.1%}"


def test_real_scam_screenshot_is_flagged():
    """Text OCR'd from a real WhatsApp scam, not from the synthetic corpus."""
    real = (
        "boleh saja tempah lock 600 dulu then set date time for viewer "
        "if takjadi akan refund ye "
        "saya tkda bank sebab itu saya guna tng "
        "sebab ada yang tnya juga"
    )
    found = flags(normalise(real))
    assert "upfront_payment" in found
    assert "pay_before_viewing" in found
    assert "refund_promise" in found
    assert "non_bank_channel" in found


# A second real scam, from a conversation that appears in no split. Every
# phrasing below was missed by the first version of these patterns.
@pytest.mark.parametrize("label,text", [
    ("refund_promise", "kalau tengok umah tak sesuai saya refund balik sepenuh nya"),
    ("rush_language", "jangan lamabt saja sebab wssp non stop masuk"),
    ("competition_pressure", "jangan lamabt saja sebab wssp non stop masuk"),
    ("competition_pressure", "selagi belum confirm masih terbuka mana yang dulu je"),
    ("deadline_pressure", "booking rm500 kena bayar malam ini kan"),
    ("deadline_pressure", "kalau nak tempah sebelum 10pm ya"),
    ("deadline_pressure", "saya lock 10 pm insyallah"),
    ("personal_details_request", "nama penuh status pekerjaan tarikh masuk"),
    ("upfront_payment", "bayar booking rm500 sekarang"),
])
def test_second_real_scam_phrasings(label, text):
    assert label in flags(normalise(text)), f"{label} missed: {text}"


def test_a_deadline_alone_is_not_a_payment_deadline():
    """Arranging a viewing time is not a payment clock."""
    assert "deadline_pressure" not in flags("boleh datang tengok rumah sebelum 5pm")
    assert "deadline_pressure" not in flags("saya free hari ini selepas 3pm")


# --- legitimacy signals ----------------------------------------------------
#
# Measured on the labelled corpus, every legitimacy signal that fires at all
# fires MORE often on scams than on genuine chats: scammers imitate legitimacy
# ("transfer to the owner company account"). So a legit signal only counts
# when no red flag fired.

from app.layer1.red_flags import analyse  # noqa: E402


def legit(text):
    return {s["id"] for s in analyse(normalise(text))["legit_signals"]}


def withheld(text):
    return {s["id"] for s in analyse(normalise(text))["legit_signals_withheld"]}


@pytest.mark.parametrize("signal,text", [
    ("viewing_arranged", "i plan to visit on 20/8 if you are free"),
    ("viewing_arranged", "I'm available at either 11am or 2pm on Saturday"),
    ("in_person_handover", "Can we meet on 28/8 to handover the keys?"),
    ("payment_at_handover", "we settle balance payment when we meet"),
    ("platform_agreement", "Agreement is ready, please check and sign the agreement"),
    ("platform_agreement", "complete the signing process on ibilik"),
])
def test_legit_signal_fires(signal, text):
    assert signal in legit(text), f"{signal} missed: {text}"


def test_legit_language_next_to_a_red_flag_is_withheld():
    """The scammer's 'company account' must never read as reassurance."""
    text = "transfer to the owner company account, kena bayar booking dulu"
    assert "company_account" not in legit(text)
    assert "company_account" in withheld(text)


def test_legit_signals_survive_when_nothing_is_wrong():
    text = "Agreement is ready. Can we meet on 28/8 to handover the keys?"
    assert legit(text) >= {"platform_agreement", "in_person_handover"}
    assert withheld(text) == set()


def test_real_legitimate_conversation_gets_its_evidence():
    """The iBilik chat that scored 0.9997 had zero layer 1 output before.

    Not a clean test: these signals were written after reading it.
    """
    import io
    import os

    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "eval", "results", "blind_legit", "diagnosis", "transcript_a_no_labels.txt",
    )
    if not os.path.exists(path):
        pytest.skip("transcript not present")
    result = analyse(normalise(io.open(path, encoding="utf-8").read()))
    assert result["red_flags"] == []
    assert len(result["legit_signals"]) >= 3
