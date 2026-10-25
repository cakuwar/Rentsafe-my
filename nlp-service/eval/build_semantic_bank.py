"""Build the tactic example bank for the semantic red-flag experiment.

Sources, and only these (the author's rule for this experiment):
  1. layer 1's own rules - each example below was written as a sentence that
     rule matches, in BM, English or Manglish, and the build REFUSES any example
     its tactic's rule does not flag (app/layer1/red_flags.py, run through the
     normaliser exactly as /classify runs it);
  2. the development scam chat (the real scam screenshots, redacted, in
     training/gates.json) - an owner message is added to a tactic only if that
     tactic's layer 1 rule fires on it. No hand-labelling.

Never from the minimal-pair test split or data/test_real. Because the author of
this bank also wrote the held-out test sentences, every example is compared
with every line of the minimal-pair test split and rejected if it is a near
duplicate (difflib ratio >= 0.8); the closest match is reported either way.

    python eval/build_semantic_bank.py

Writes app/layer1/semantic_tactics.json (experimental; not read by the service).
"""
import difflib
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NLP = os.path.dirname(HERE)
ROOT = os.path.dirname(NLP)
sys.path.insert(0, NLP)

import pandas as pd

from app.layer1.red_flags import analyse
from app.normaliser.normaliser import normalise

OUT = os.path.join(NLP, "app", "layer1", "semantic_tactics.json")
NEAR_DUPLICATE = 0.8

# Tactic -> the layer 1 rule(s) it extends.
TACTIC_RULES = {
    "viewing_refused": ["viewing_denial"],
    "pay_before_viewing": ["pay_before_viewing"],
    "booking_fee": ["upfront_payment"],
    "keys_by_courier": ["key_courier"],
    "owner_away": ["remote_owner"],
    "pay_other_account": ["third_party_account"],
    "deadline_urgency": ["deadline_pressure", "rush_language"],
    "competition": ["competition_pressure"],
}

# Written from each rule's patterns (see the rule in app/layer1/red_flags.py).
AUTHORED = {
    "viewing_refused": [
        ("ms", "Maaf, rumah tu tak boleh tengok sekarang."),
        ("ms", "Tidak boleh lawat unit tu, maaf."),
        ("ms", "Tidak dapat masuk ke unit sehingga bulan depan."),
        ("en", "Sorry, I cannot show you the unit."),
        ("en", "Viewing is not possible at the moment."),
        ("en", "No viewing for this unit, sorry."),
        ("en", "We cannot open the room for you."),
        ("mix", "Sorry bro, x boleh view dulu."),
        ("mix", "Unit tu tk dpt viewing lagi ya."),
        ("mix", "viewing not allowed buat masa ni."),
    ],
    "pay_before_viewing": [
        ("ms", "Bayar dulu baru boleh tengok rumah."),
        ("ms", "Kena transfer deposit sebelum lihat unit."),
        ("ms", "Lepas transfer saya bagi masa untuk tengok."),
        ("en", "Transfer the deposit first, then you can view."),
        ("en", "You can see the room after you pay the booking."),
        ("en", "Pay the deposit before viewing."),
        ("mix", "bayar booking dulu then baru boleh view."),
        ("mix", "lock dulu with deposit, then I bagi time viewing."),
        ("mix", "after you transfer, I'll arrange the key."),
    ],
    "booking_fee": [
        ("ms", "Kena bayar booking RM300 untuk simpan bilik."),
        ("ms", "Deposit dulu untuk lock bilik ni."),
        ("ms", "Tempah dulu dengan RM200, baki bayar kemudian."),
        ("en", "There is a booking fee of RM500 to hold the room."),
        ("en", "You need to reserve it with a small payment."),
        ("en", "A reservation fee is required to lock the unit."),
        ("mix", "booking RM250 dulu ya, baru saya simpan bilik."),
        ("mix", "kena bayar awal sikit untuk lock room."),
    ],
    "keys_by_courier": [
        ("ms", "Saya pos kunci ke alamat awak."),
        ("ms", "Kunci akan dipos selepas bayaran diterima."),
        ("ms", "Nanti saya hantar kunci guna kurier."),
        ("en", "I will post the keys to you."),
        ("en", "I can courier the keys to your office."),
        ("en", "I'll mail you the key once it's settled."),
        ("mix", "Access card akan dipos, no need jumpa."),
        ("mix", "nanti I pos kunci ke you."),
    ],
    "owner_away": [
        ("ms", "Saya di luar negara sekarang."),
        ("ms", "Maaf, saya outstation minggu ni."),
        ("ms", "Saya tiada di Malaysia bulan ni."),
        ("en", "I'm overseas at the moment."),
        ("en", "I'm not in town until next month."),
        ("en", "Currently I'm overseas for work."),
        ("mix", "sy kat luar negara, so tak dapat jumpa."),
        ("mix", "I outstation ni, balik next month."),
        ("mix", "I tiada di sini, kerja luar negara."),
    ],
    "pay_other_account": [
        ("ms", "Bank in ke akaun adik saya ya."),
        ("ms", "Sila bayar ke akaun atas nama orang lain."),
        ("ms", "Nama akaun lain, itu akaun abang saya."),
        ("en", "Please transfer to my agent instead."),
        ("en", "Transfer to my friend, he handles the collection."),
        ("en", "Payment goes to the company account."),
        ("mix", "you bank in ke akaun isteri I ya."),
        ("mix", "transfer to boss punya akaun ok."),
        ("mix", "akaun syarikat, bukan akaun I."),
    ],
    "deadline_urgency": [
        ("ms", "Bayar sebelum 8 malam ini ya."),
        ("ms", "Kena transfer hari ini juga."),
        ("ms", "Jangan lambat, bilik ni laju."),
        ("en", "Please transfer before 6pm today."),
        ("en", "Transfer within 2 hours or I release the room."),
        ("en", "It's urgent, please hurry."),
        ("mix", "booking kena settle tonight ok."),
        ("mix", "cepat sikit ya, lock by 9pm."),
        ("mix", "urgent bro, bayar sekarang juga."),
    ],
    "competition": [
        ("ms", "Ramai orang tengah tanya pasal bilik ni."),
        ("ms", "Ada yang lain minat juga."),
        ("ms", "Siapa cepat dia dapat."),
        ("en", "Many people are asking about this unit."),
        ("en", "Many others are interested, first come first serve."),
        ("en", "It's first come first serve."),
        ("mix", "wssp non stop masuk pasal unit ni."),
        ("mix", "ramai minat, mana yang dulu dapat."),
        ("mix", "ada yang tanya jgk, so decide cepat."),
    ],
}


def messages(text):
    """(speaker, text) per message: a labelled line plus its unlabelled continuations."""
    out = []
    for line in text.split("\n"):
        if not line.strip():
            continue
        head, _, rest = line.partition(": ")
        if head in ("Owner", "Renter") and rest:
            out.append([head, rest.strip()])
        elif out:
            out[-1][1] += " " + line.strip()
        else:
            out.append(["Renter", line.strip()])
    return [(speaker, body) for speaker, body in out]


def flags(sentence):
    return set(analyse(normalise(sentence))["red_flags"])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    bank = {tactic: [] for tactic in TACTIC_RULES}

    failures = []
    for tactic, examples in AUTHORED.items():
        for lang, sentence in examples:
            fired = flags(sentence) & set(TACTIC_RULES[tactic])
            if not fired:
                failures.append((tactic, sentence, sorted(flags(sentence))))
            bank[tactic].append({"text": sentence, "lang": lang, "source": "layer1_rule",
                                 "rule": sorted(fired)})
    if failures:
        for failure in failures:
            print("NOT MATCHED BY ITS RULE:", failure)
        sys.exit("fix the examples above - each must be an instance of its layer 1 rule")

    gates = json.load(open(os.path.join(NLP, "training", "gates.json"), encoding="utf-8"))
    dev = [body for speaker, body in messages(gates["real_scam_production"]["text"])
           if speaker == "Owner"]
    for body in dev:
        fired = flags(body)
        for tactic, rules in TACTIC_RULES.items():
            if fired & set(rules):
                bank[tactic].append({"text": body, "lang": "dev", "source": "dev_scam_chat",
                                     "rule": sorted(fired & set(rules))})

    # Guard against the author's knowledge of the held-out test sentences.
    test = pd.read_csv(os.path.join(ROOT, "data", "processed", "augmented", "minimal_pairs_test.csv"))
    test_lines = sorted({body for t in test["text"] for _, body in messages(t)})
    rejected = []
    for tactic, examples in bank.items():
        kept = []
        for example in examples:
            best = max(test_lines, key=lambda line: difflib.SequenceMatcher(
                None, example["text"].lower(), line.lower()).ratio())
            ratio = difflib.SequenceMatcher(None, example["text"].lower(), best.lower()).ratio()
            example["closest_test_line"] = {"ratio": round(ratio, 3), "line": best}
            (rejected if ratio >= NEAR_DUPLICATE else kept).append(example)
        bank[tactic] = kept

    counts = {tactic: len(examples) for tactic, examples in bank.items()}
    payload = {
        "status": "EXPERIMENTAL - not read by the service (eval/semantic_flags.py only)",
        "built_by": "eval/build_semantic_bank.py",
        "tactic_rules": TACTIC_RULES,
        "near_duplicate_ratio": NEAR_DUPLICATE,
        "rejected_as_near_duplicates": rejected,
        "counts": counts,
        "tactics": bank,
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    payload["sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)

    print("examples per tactic:", counts)
    print("dev-chat examples:", sum(e["source"] == "dev_scam_chat" for es in bank.values() for e in es))
    print("rejected as near-duplicates of a test line:", len(rejected))
    worst = sorted((e["closest_test_line"]["ratio"], t, e["text"], e["closest_test_line"]["line"])
                   for t, es in bank.items() for e in es)[-5:]
    print("closest remaining examples to any test line:")
    for ratio, tactic, text, line in reversed(worst):
        print(f"  {ratio:.3f} [{tactic}] {text!r}  ~  {line!r}")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
