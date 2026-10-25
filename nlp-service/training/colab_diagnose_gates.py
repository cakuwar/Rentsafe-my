# Written for retrain RUN 1, which cut windows at fixed token offsets; its
# window_detail() reproduces those windows on purpose. Result:
# eval/results/v3_run1_diagnosis.json. The notebook now cuts between messages.
#
# Paste as a NEW cell at the end of train_colab_v3.ipynb, in the same session,
# after section 7 has run. Diagnosis only: it changes nothing and does not
# affect the verdict. Uses the notebook's own globals (best, tokenizer,
# windowed_margin, probability, gates, TEMPERATURE, MAX_LENGTH, device).
#
# Answers: why does the OCR text of the real legitimate chat score 0.78 when
# the clean transcript of the same chat scores 0.14?
#   1. per-window scores  - which part of the conversation is responsible
#   2. leave-one-line-out - which lines push the score toward SCAM
#   3. noise-only test    - same OCR text minus lines with no counterpart in the
#                           hand transcript (photo captions, stray glyphs)

import re

import numpy as np
import torch


def window_detail(text):
    ids = tokenizer(text, add_special_tokens=False)["input_ids"]
    body = MAX_LENGTH - 2
    starts = list(range(0, max(1, len(ids) - body + 1), 256)) or [0]
    if starts[-1] + body < len(ids):
        starts.append(max(0, len(ids) - body))
    rows = []
    with torch.no_grad():
        for s in starts:
            chunk = ids[s:s + body]
            enc = tokenizer.prepare_for_model(chunk, add_special_tokens=True, return_tensors="pt")
            enc = {k: (v.unsqueeze(0) if v.dim() == 1 else v).to(device) for k, v in enc.items()}
            logits = best(**enc).logits[0].float()
            p = float(probability(float(logits[scam_index] - logits[legit_index])))
            words = tokenizer.decode(chunk).replace("\n", " | ")
            rows.append((s, len(chunk), p, words[:60], words[-60:]))
    return rows


def p_of(text):
    return float(probability(windowed_margin(text)))


def line_influence(text):
    lines = text.split("\n")
    base = p_of(text)
    out = []
    for i, line in enumerate(lines):
        rest = "\n".join(lines[:i] + lines[i + 1:])
        out.append((base - p_of(rest), i, line))
    out.sort(reverse=True)
    return base, out


def _words(text):
    return set(re.findall(r"[a-z]{3,}", text.lower()))


CLEAN_WORDS = [_words(l.split(": ", 1)[-1])
               for l in gates["real_legit_clean"]["text"].split("\n") if l.strip()]


def has_counterpart(line):
    """Half or more of the line's words occur in one line of the hand transcript.
    Lines below that are OCR noise (photo captions, stray glyphs)."""
    words = _words(line.split(": ", 1)[-1])
    return bool(words) and max(len(words & c) / len(words) for c in CLEAN_WORDS) >= 0.5


diagnosis = {}
for name in ["real_legit_production", "real_legit_clean", "ablation_mechanics_removed"]:
    text = gates[name]["text"]
    print("=" * 96)
    print(f"{name}   ({len(text.splitlines())} lines)")
    for s, n, p, head, tail in window_detail(text):
        print(f"  window from token {s:>4} ({n} tokens): p={p:.4f}")
        print(f"      starts: {head}")
        print(f"      ends:   {tail}")
    base, influence = line_influence(text)
    print(f"\n  whole text p={base:.4f}")
    print("  lines that push toward SCAM (removing them lowers p):")
    for d, i, line in influence[:10]:
        print(f"    {d:+.4f}  [{i:>2}] {line[:100]}")
    print("  lines that push toward LEGITIMATE (removing them raises p):")
    for d, i, line in influence[-5:]:
        print(f"    {d:+.4f}  [{i:>2}] {line[:100]}")
    diagnosis[name] = {"p": base, "influence": [(round(d, 4), i, l) for d, i, l in influence]}

prod = gates["real_legit_production"]["text"].split("\n")
kept = [l for l in prod if has_counterpart(l)]
print("=" * 96)
print(f"real_legit_production with OCR-noise lines removed: {len(prod)} -> {len(kept)} lines")
print(f"  p = {p_of(chr(10).join(kept)):.4f}   (was {p_of(chr(10).join(prod)):.4f})")
print("  removed:", [l[:40] for l in prod if not has_counterpart(l)])
unlabelled = "\n".join(l.split(": ", 1)[-1] for l in prod)
print(f"  speaker labels stripped: p = {p_of(unlabelled):.4f}")

with open("v3_run1_diagnosis.json", "w") as handle:
    json.dump(diagnosis, handle, indent=1)
files.download("v3_run1_diagnosis.json")
