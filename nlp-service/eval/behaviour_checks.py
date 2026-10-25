"""Behavioural probes of the deployed classifier.

Accuracy on the validation set cannot answer these, because the model scores
1.0000 there. Each check targets something the headline number hides.

  a) Group ablation - remove every scam mechanic from a scam conversation at
     once. If the score stays high, the model is matching the template rather
     than the scam. Single-line ablation could not answer this: XLM-R's output
     is saturated, so removing any one line moved it by less than 0.001.
  b) English-only conversations - training scams are almost all code-switched
     Malay. These are AUTHOR-WRITTEN, so they show whether the model generalises
     to English phrasing, not how it performs in the wild.
  c) Benign short messages - how often an ordinary one-line reply is flagged.
  d) macro-F1 and MCC on validation, which are informative under class
     imbalance in a way that binary F1 is not.
  e) Whether the conversation used in MODEL_COMPARISON.md §7.1 echoes a training
     template, which decides how much that section's result is worth.

    python eval/behaviour_checks.py

Writes eval/results/behaviour_checks.json.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    matthews_corrcoef,
    precision_recall_fscore_support,
)
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app import config

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "..", "data", "processed", "random")
OUT = os.path.join(HERE, "results", "behaviour_checks.json")
LABELS = {"LEGITIMATE": 0, "SCAM": 1}
MAX_LENGTH = 256

# The conversation from MODEL_COMPARISON.md §7.1, as OCR produced it.
SECTION_71 = [
    "Renter: Hi, is the room still available?",
    "Owner: Yes it is. Nak masuk bila ya?",
    "Renter: Early next month.",
    "Renter: Boleh pergi viewing dulu tak?",
    "Owner: I'm outstation in Sabah now.",
    "Owner: Cannot open the unit sorry.",
    "Owner: Kalau nak lock the room,",
    "Owner: transfer deposit RM800 dulu.",
    "Renter: Can I see it first?",
    "Owner: Ramai orang tengah tanya.",
    "Owner: Lepas transfer saya pos kunci.",
]

# Every line carrying a scam mechanic, removed together in check (a).
SCAM_MECHANIC_LINES = {
    "Owner: I'm outstation in Sabah now.",
    "Owner: Cannot open the unit sorry.",
    "Owner: Kalau nak lock the room,",
    "Owner: transfer deposit RM800 dulu.",
    "Owner: Ramai orang tengah tanya.",
    "Owner: Lepas transfer saya pos kunci.",
}

# AUTHOR-WRITTEN. Not collected from real chats, not evidence of field
# performance. They exist to probe an English-language gap the corpus cannot.
ENGLISH_SCAMS = [
    [
        "Renter: Hi, is the studio still available?",
        "Owner: Yes it is. When would you like to move in?",
        "Renter: Next month. Could I view it this weekend?",
        "Owner: I'm working in Singapore at the moment, so I can't open it.",
        "Renter: Is there anyone who could show me around?",
        "Owner: No, but I can hold it for you with a RM500 booking fee.",
        "Renter: Can I see it before I pay?",
        "Owner: Many people are asking. Pay first and I'll courier the keys.",
    ],
    [
        "Renter: Good evening, I saw your listing for the condo.",
        "Owner: Hello, still available. Two months deposit, one month advance.",
        "Renter: Can we arrange a viewing?",
        "Owner: I'm overseas until next year, the unit is locked.",
        "Renter: Then how do I see it?",
        "Owner: I'll send photos and a video. Transfer the deposit to secure it.",
        "Renter: I'd rather view first.",
        "Owner: If you don't proceed I refund everything, no problem.",
    ],
    [
        "Renter: Hi, is the room near the university still free?",
        "Owner: Yes. Are you a student?",
        "Renter: Yes, starting in September.",
        "Owner: Great. To reserve it I need a RM300 holding fee today.",
        "Renter: Could I come and look on Saturday?",
        "Owner: Viewing is only after booking, sorry, company policy.",
        "Renter: That seems unusual.",
        "Owner: It's standard. Send me the receipt once you transfer.",
    ],
    [
        "Renter: Hello, enquiring about the apartment advertised.",
        "Owner: Hi. Rent is RM900, very cheap for that area.",
        "Renter: It does seem below market. Can I view it?",
        "Owner: My agent handles viewings but he is away this month.",
        "Renter: When will he be back?",
        "Owner: Not sure. Better to secure it now, pay to my company account.",
        "Renter: Can you show proof you own it?",
        "Owner: Just trust me, I'm not a scammer. Others already paid.",
    ],
    [
        "Renter: Is the unit at Mont Kiara still open?",
        "Owner: Yes, but I have three people interested.",
        "Renter: I'd like to see it first.",
        "Owner: I'm outstation. I can post the access card to you.",
        "Renter: I'd prefer to meet in person.",
        "Owner: No need to meet. Pay one month rent and I'll mail the keys.",
        "Renter: How do I know the unit exists?",
        "Owner: I'll send a video call later. Transfer before 9pm tonight.",
    ],
]

ENGLISH_LEGIT = [
    [
        "Renter: Hi, is the studio still available?",
        "Owner: Yes it is. When are you looking to move in?",
        "Renter: Early next month. Could I view it this weekend?",
        "Owner: Sure, Saturday afternoon works. I'll meet you at the lobby.",
        "Renter: How much is the deposit?",
        "Owner: Two months plus half a month utilities, paid on signing.",
        "Renter: Is the agreement stamped?",
        "Owner: Yes, we stamp it at the office. See you Saturday.",
    ],
    [
        "Renter: Good evening, enquiring about the condo listing.",
        "Owner: Hello. RM1800 a month, partially furnished.",
        "Renter: Can I arrange a viewing?",
        "Owner: Of course. I'm free Tuesday or Thursday evening.",
        "Renter: Thursday suits me.",
        "Owner: Great. I'll bring the title and the tenancy agreement.",
        "Renter: Thank you, see you then.",
        "Owner: See you Thursday.",
    ],
    [
        "Renter: Hi, is the room near the university still free?",
        "Owner: It is. Are you a student?",
        "Renter: Yes, starting September.",
        "Owner: No problem. Come and see it whenever suits you.",
        "Renter: Would Saturday morning be alright?",
        "Owner: Saturday is fine. Deposit is one month, paid after you sign.",
        "Renter: Perfect, thank you.",
        "Owner: See you Saturday.",
    ],
    [
        "Renter: Hello, enquiring about the apartment advertised.",
        "Owner: Hi. RM1400, available from the first of next month.",
        "Renter: Could I view it before deciding?",
        "Owner: Yes, I'd prefer you did. When are you free?",
        "Renter: This Sunday?",
        "Owner: Sunday works. I'll be there to open up and answer questions.",
        "Renter: Do you need documents from me?",
        "Owner: Just your details when we sign, nothing before that.",
    ],
    [
        "Renter: Is the unit at Mont Kiara still open?",
        "Owner: Yes. Would you like to have a look?",
        "Renter: Please, if that's possible this week.",
        "Owner: Wednesday evening, around seven?",
        "Renter: That works. What's the deposit arrangement?",
        "Owner: Two plus one, paid when we sign the tenancy. Nothing upfront.",
        "Renter: Sounds good, thank you.",
        "Owner: See you Wednesday.",
    ],
]

BENIGN_SHORT = [
    "Sure, you can view the unit this Saturday.",
    "The rent is RM1200 a month, deposit is two months as usual.",
    "Boleh datang tengok rumah hujung minggu ni, saya ada.",
    "Yes it is still available, when would you like to see it?",
    "We can sign the tenancy agreement at the office.",
    "Sewa rm900 sebulan, bayar selepas sign agreement.",
    "I'll be there at 3pm to open the unit for you.",
    "No problem, take your time to decide.",
]


def load_model():
    tokenizer = AutoTokenizer.from_pretrained(config.FINETUNED_MODEL_DIR)
    model = AutoModelForSequenceClassification.from_pretrained(
        config.FINETUNED_MODEL_DIR
    )
    model.eval()
    scam_index = {
        str(label).upper(): index
        for label, index in (model.config.label2id or {}).items()
    }.get("SCAM", 1)
    return tokenizer, model, scam_index


def p_scam(tokenizer, model, scam_index, texts, batch=16):
    out = []
    with torch.no_grad():
        for start in range(0, len(texts), batch):
            encoded = tokenizer(
                texts[start:start + batch], truncation=True,
                max_length=MAX_LENGTH, padding=True, return_tensors="pt",
            )
            out.extend(model(**encoded).logits.softmax(-1)[:, scam_index].tolist())
    return out


def shingles(text, size=5):
    words = re.findall(r"[a-z]+", text.lower())
    return {tuple(words[i:i + size]) for i in range(len(words) - size + 1)}


def main():
    tokenizer, model, scam_index = load_model()
    results = {"model": config.PRIMARY_MODEL,
               "weights": os.path.basename(config.FINETUNED_MODEL_DIR)}

    # --- (a) group ablation ------------------------------------------------
    print("=" * 66)
    print("a) GROUP ABLATION - all scam mechanics removed at once")
    print("=" * 66)
    full = "\n".join(SECTION_71)
    stripped = "\n".join(l for l in SECTION_71 if l not in SCAM_MECHANIC_LINES)
    only_mechanics = "\n".join(l for l in SECTION_71 if l in SCAM_MECHANIC_LINES)
    scores = p_scam(tokenizer, model, scam_index, [full, stripped, only_mechanics])

    print(f"  full conversation           p(scam) {scores[0]:.4f}")
    print(f"  all scam mechanics removed  p(scam) {scores[1]:.4f}")
    print(f"  scam mechanics only         p(scam) {scores[2]:.4f}")
    verdict = (
        "TEMPLATE-MATCHING: score stayed high without any scam mechanic"
        if scores[1] >= 0.5 else
        "READS THE MECHANICS: removing them collapsed the score"
    )
    print(f"  -> {verdict}")
    results["group_ablation"] = {
        "full": round(scores[0], 4),
        "mechanics_removed": round(scores[1], 4),
        "mechanics_only": round(scores[2], 4),
        "removed_lines": sorted(SCAM_MECHANIC_LINES),
        "verdict": verdict,
    }

    # --- (b) English-only conversations -----------------------------------
    print()
    print("=" * 66)
    print("b) ENGLISH-ONLY CONVERSATIONS (author-written, not collected)")
    print("=" * 66)
    scam_texts = ["\n".join(c) for c in ENGLISH_SCAMS]
    legit_texts = ["\n".join(c) for c in ENGLISH_LEGIT]
    scam_scores = p_scam(tokenizer, model, scam_index, scam_texts)
    legit_scores = p_scam(tokenizer, model, scam_index, legit_texts)

    print("  scams (want >= 0.5):")
    for index, score in enumerate(scam_scores, 1):
        print(f"    {index}. p(scam) {score:.4f}  {'OK' if score >= 0.5 else 'MISSED'}")
    print("  legitimate (want < 0.5):")
    for index, score in enumerate(legit_scores, 1):
        print(f"    {index}. p(scam) {score:.4f}  "
              f"{'OK' if score < 0.5 else 'FALSE ALARM'}")
    caught = sum(1 for s in scam_scores if s >= 0.5)
    cleared = sum(1 for s in legit_scores if s < 0.5)
    print(f"  -> {caught}/5 scams caught, {cleared}/5 legitimate cleared")
    results["english_only"] = {
        "note": "AUTHOR-WRITTEN probes, not collected data",
        "scam_scores": [round(s, 4) for s in scam_scores],
        "legit_scores": [round(s, 4) for s in legit_scores],
        "scams_caught": caught,
        "legit_cleared": cleared,
    }

    # --- (c) benign short messages ----------------------------------------
    print()
    print("=" * 66)
    print("c) BENIGN SHORT MESSAGES - how many get flagged")
    print("=" * 66)
    short_scores = p_scam(tokenizer, model, scam_index, BENIGN_SHORT)
    flagged = 0
    for text, score in zip(BENIGN_SHORT, short_scores):
        mark = "FLAGGED" if score >= 0.5 else "ok"
        flagged += score >= 0.5
        print(f"  {score:.4f} {mark:<8} {text[:52]}")
    print(f"  -> {flagged}/{len(BENIGN_SHORT)} benign messages flagged as scam")
    results["benign_short"] = {
        "scores": [round(s, 4) for s in short_scores],
        "flagged": int(flagged),
        "total": len(BENIGN_SHORT),
    }

    # --- (d) macro-F1 and MCC ---------------------------------------------
    print()
    print("=" * 66)
    print("d) VALIDATION METRICS")
    print("=" * 66)
    frame = pd.read_csv(os.path.join(DATA, "val.csv"))
    frame["label"] = frame["label"].str.upper().replace({"LEGIT": "LEGITIMATE"})
    actual = np.array([LABELS[label] for label in frame["label"]])
    predicted = (
        np.array(p_scam(tokenizer, model, scam_index, frame["text"].tolist())) >= 0.5
    ).astype(int)
    precision, recall, binary_f1, _ = precision_recall_fscore_support(
        actual, predicted, average="binary", zero_division=0
    )
    metrics = {
        "accuracy": round(float(accuracy_score(actual, predicted)), 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "binary_f1": round(float(binary_f1), 4),
        "macro_f1": round(float(f1_score(actual, predicted, average="macro")), 4),
        "mcc": round(float(matthews_corrcoef(actual, predicted)), 4),
    }
    for name, value in metrics.items():
        print(f"  {name:<12} {value}")
    results["validation_metrics"] = metrics

    # --- (e) is §7.1 a training template? ---------------------------------
    print()
    print("=" * 66)
    print("e) DOES THE SECTION 7.1 CONVERSATION ECHO A TRAINING TEMPLATE?")
    print("=" * 66)
    train = pd.read_csv(os.path.join(DATA, "train.csv"))
    target = shingles(full)
    best, best_group = 0.0, None
    for _, row in train.iterrows():
        overlap = target & shingles(str(row["text"]))
        share = len(overlap) / max(1, len(target))
        if share > best:
            best, best_group = share, row.get("source_group")
    print(f"  highest 5-gram overlap with any training conversation: {best:.1%}")
    print(f"  closest training source_group: {best_group}")
    echoes = best >= 0.10
    print("  -> " + (
        "ECHOES TRAINING DATA: the §7.1 result is partly in-distribution"
        if echoes else
        "distinct from training conversations at the 5-gram level"
    ))
    results["section_71_template_check"] = {
        "max_5gram_overlap": round(float(best), 4),
        "closest_source_group": None if best_group is None else str(best_group),
        "echoes_training": bool(echoes),
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as handle:
        json.dump(results, handle, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
