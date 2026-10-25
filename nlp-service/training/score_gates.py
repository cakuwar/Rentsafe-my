"""Score a model directory against training/gates.json.

Used locally to baseline the deployed model, and the same logic runs inside the
retraining notebook so before/after numbers come from one definition.

Long inputs are scored with sliding windows (see app/layer2/classifier.py), so a
700-token conversation is read in full rather than cut to its first third.

    python training/score_gates.py [model_dir]

Writes eval/results/gates_<model>.json.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NLP = os.path.dirname(HERE)
sys.path.insert(0, NLP)

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.layer2.classifier import _message_windows, _temperature_of  # noqa: E402


def windowed_probability(tokenizer, model, scam_index, text):
    """Raw P(scam) over the whole text: max across the SERVICE's windows
    (cut between messages - app/layer2/classifier.py), temperature 1, which is
    what the acceptance criteria are judged on."""
    scores = []
    with torch.no_grad():
        for window in _message_windows(tokenizer, text):
            encoded = tokenizer.prepare_for_model(
                window, add_special_tokens=True, return_tensors="pt"
            )
            encoded = {k: v.unsqueeze(0) if v.dim() == 1 else v for k, v in encoded.items()}
            logits = model(**encoded).logits[0]
            scores.append(float(logits[scam_index] - logits[1 - scam_index]))
    return max(scores)


def _sigmoid(margin, temperature=1.0):
    import math
    return 1.0 / (1.0 + math.exp(-margin / temperature))


def score(model_dir, gates_path=os.path.join(HERE, "gates.json")):
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)
    model.eval()
    scam_index = {
        str(k).upper(): v for k, v in (model.config.label2id or {}).items()
    }.get("SCAM", 1)

    gates = json.load(open(gates_path, encoding="utf-8"))
    results = {}
    passed = 0
    total = 0
    temperature = _temperature_of(model.config)
    print(f"{'gate':<30}{'expect':>12}{'p(scam)':>10}{'served':>9}  result"
          f"   (served = what the API returns, temperature {temperature:.3f})")
    print("-" * 72)
    for name, gate in gates.items():
        if name.startswith("_"):
            continue
        margin = windowed_probability(tokenizer, model, scam_index, gate["text"])
        probability, served = _sigmoid(margin), _sigmoid(margin, temperature)
        predicted = "SCAM" if probability >= 0.5 else "LEGITIMATE"
        ok = predicted == gate["expect"]
        passed += ok
        total += 1
        results[name] = {
            "expect": gate["expect"], "p_scam": round(probability, 4),
            "p_scam_served": round(served, 4),
            "windows": len(_message_windows(tokenizer, gate["text"])), "passed": ok,
        }
        print(f"{name:<30}{gate['expect']:>12}{probability:>10.4f}"
              f"{served:>9.4f}  {'PASS' if ok else 'FAIL'}")
    print(f"\n{passed}/{total} gates passed")
    return {"passed": passed, "total": total, "gates": results}


if __name__ == "__main__":
    from app import config

    target = sys.argv[1] if len(sys.argv) > 1 else config.FINETUNED_MODEL_DIR
    report = score(target)
    out = os.path.join(NLP, "eval", "results",
                       f"gates_{os.path.basename(os.path.normpath(target))}.json")
    with open(out, "w") as handle:
        json.dump(report, handle, indent=2)
    print(f"wrote {out}")
