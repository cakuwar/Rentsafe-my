# Retrain RUN 2 diagnosis. Paste as a NEW cell at the end of train_colab_v3.ipynb,
# in the SAME session as run 2, after section 7 has run. Diagnosis only: it
# changes nothing and does not affect the verdict. Uses the notebook's own
# globals (best, tokenizer, message_windows, windowed_margin, probability,
# pair_test, pair_dev, gates, m_dev, y_dev, TEMPERATURE, device, ...).
# Downloads v3_run2_diagnosis.json at the end.
#
# Questions:
#   A. Are the pair-test errors missed scams or false alarms?
#   B. Wording seen in training vs new wording: how big is the gap?
#   C. "Core" rows: do they fail more when the only scam line is
#      "I can't show you the unit" (no payment demand)?
#   D. Which pairs fail, and on which sentences?
#   E. Real legit chat (clean + OCR) and the English scam: which window and
#      which lines push the score the wrong way?
#   F. Why the calibration temperature came out at 0.176.

import json

import numpy as np
import pandas as pd
import torch

out = {"run": 2}
SEP = "=" * 96


def p_of(text):
    return float(probability(windowed_margin(text)))


def lines_of(text):
    return [l for l in text.split("\n") if l.strip()]


pt = pair_test.copy()
if "p" not in pt or "correct" not in pt:
    pt["p"] = [p_of(t) for t in pt["text"]]
    pt["correct"] = (pt["p"] >= 0.5) == (pt["label"] == "SCAM")

# ---------------------------------------------------------------------------
print(SEP)
print("A. WHERE THE ERRORS ARE  (held-out wording; SCAM rows wrong = missed scams,")
print("   LEGITIMATE rows wrong = false alarms)")
out["A_by_kind_label"] = {}
for (kind_name, label), grp in pt.groupby(["kind", "label"]):
    acc, mean_p = float(grp["correct"].mean()), float(grp["p"].mean())
    out["A_by_kind_label"][f"{kind_name}/{label}"] = {
        "rows": int(len(grp)), "accuracy": round(acc, 4), "mean_p_scam": round(mean_p, 4)}
    print(f"  {kind_name:<10} {label:<11} rows {len(grp):>3}   accuracy {acc:.3f}   "
          f"mean p(scam) {mean_p:.3f}")

# ---------------------------------------------------------------------------
print(SEP)
print("B. SEEN WORDING vs NEW WORDING  (same generator; pairs the model never trained on)")
dev_full = pair_dev[pair_dev["kind"] == "full"].copy()
dev_full["p"] = [p_of(t) for t in dev_full["text"]]
dev_full["correct"] = (dev_full["p"] >= 0.5) == (dev_full["label"] == "SCAM")
seen = float(dev_full.groupby("pair_id")["correct"].all().mean())
test_full = pt[pt["kind"] == "full"]
new = float(test_full.groupby("pair_id")["correct"].all().mean())
out["B_seen_vs_new"] = {"seen_wording_pair_accuracy": round(seen, 4),
                        "seen_pairs": int(dev_full["pair_id"].nunique()),
                        "new_wording_pair_accuracy": round(new, 4),
                        "new_pairs": int(test_full["pair_id"].nunique())}
print(f"  wording seen in training (dev pairs):  pair accuracy {seen:.3f}  "
      f"({dev_full['pair_id'].nunique()} pairs; used for early stopping, not trained on)")
print(f"  held-out wording (test pairs):          pair accuracy {new:.3f}  "
      f"({test_full['pair_id'].nunique()} pairs)")

# ---------------------------------------------------------------------------
print(SEP)
print("C. CORE ROWS (labelled SCAM): only 'can't show the unit' vs with a payment demand")
first_scam, scam_lines = {}, {}
for group, grp in test_full.groupby("source_group"):
    legit = grp.loc[grp["label"] == "LEGITIMATE", "text"].iloc[0].split("\n")
    scam = grp.loc[grp["label"] == "SCAM", "text"].iloc[0].split("\n")
    differ = [s for l, s in zip(legit, scam) if l != s]
    first_scam[group], scam_lines[group] = differ[0], set(differ)
cores = pt[pt["kind"] == "core"].copy()
cores["has_payment_demand"] = [
    any(l in scam_lines[g] and l != first_scam[g] for l in t.split("\n"))
    for g, t in zip(cores["source_group"], cores["text"])]
out["C_cores"] = {}
for has, grp in cores.groupby("has_payment_demand"):
    what = "viewing refused + pay/pressure" if has else "only 'can't show the unit'"
    acc = float(grp["correct"].mean())
    out["C_cores"][what] = {"rows": int(len(grp)), "called_scam": round(acc, 4),
                            "mean_p_scam": round(float(grp["p"].mean()), 4)}
    print(f"  {what:<32} rows {len(grp):>3}   called SCAM {acc:.3f}   "
          f"mean p(scam) {grp['p'].mean():.3f}")

# ---------------------------------------------------------------------------
print(SEP)
print("D. FAILING FULL PAIRS  (the lines where the twins differ)")
ok = test_full.groupby("pair_id")["correct"].all()
failing = [pid for pid, good in ok.items() if not good]
out["D_failing_pairs"] = []
for pid in failing:
    grp = test_full[test_full["pair_id"] == pid]
    legit_row = grp[grp["label"] == "LEGITIMATE"].iloc[0]
    scam_row = grp[grp["label"] == "SCAM"].iloc[0]
    diffs = [(l, s) for l, s in zip(legit_row["text"].split("\n"), scam_row["text"].split("\n"))
             if l != s]
    wrong = ("scam twin missed" if scam_row["p"] < 0.5 else "") + \
            (" + " if scam_row["p"] < 0.5 and legit_row["p"] >= 0.5 else "") + \
            ("legit twin flagged" if legit_row["p"] >= 0.5 else "")
    out["D_failing_pairs"].append({"pair_id": pid, "lang": legit_row["lang"],
                                   "p_legit_twin": round(float(legit_row["p"]), 4),
                                   "p_scam_twin": round(float(scam_row["p"]), 4),
                                   "what": wrong, "differing_lines": diffs})
for entry in out["D_failing_pairs"][:12]:
    print(f"  {entry['pair_id']} [{entry['lang']}] {entry['what']}: "
          f"legit twin {entry['p_legit_twin']:.3f}, scam twin {entry['p_scam_twin']:.3f}")
    side = 1 if "missed" in entry["what"] else 0
    for pair in entry["differing_lines"]:
        print(f"       {'scam ' if side else 'legit'}: {pair[side][:92]}")
print(f"  ({len(failing)} failing pairs in total; all are in the JSON)")


# ---------------------------------------------------------------------------
def window_scores(text):
    rows = []
    with torch.no_grad():
        for window in message_windows(text):
            enc = tokenizer.prepare_for_model(window, add_special_tokens=True, return_tensors="pt")
            enc = {k: (v.unsqueeze(0) if v.dim() == 1 else v).to(device) for k, v in enc.items()}
            logits = best(**enc).logits[0].float()
            margin = float(logits[scam_index] - logits[legit_index])
            words = tokenizer.decode(window).replace("\n", " | ")
            rows.append({"p": round(float(probability(margin)), 4), "tokens": len(window),
                         "starts": words[:60], "ends": words[-60:]})
    return rows


def influence(text):
    lines = lines_of(text)
    base = p_of("\n".join(lines))
    rows = []
    for i, line in enumerate(lines):
        rest = "\n".join(lines[:i] + lines[i + 1:])
        rows.append((round(base - p_of(rest), 4), i, line))
    rows.sort(reverse=True)
    return base, rows


print(SEP)
print("E. REAL LEGIT CHAT (clean + OCR) AND THE ENGLISH SCAM")
out["E"] = {}
for name in ["real_legit_clean", "real_legit_production", "english_courier_scam"]:
    text = gates[name]["text"]
    windows = window_scores(text)
    base, infl = influence(text)
    out["E"][name] = {"p": round(base, 4), "windows": windows, "influence": infl}
    print(f"\n  {name}  p={base:.4f}  expect {gates[name]['expect']}")
    for w in windows:
        print(f"    window p={w['p']:.4f} ({w['tokens']} tokens): '{w['starts'][:45]}' ... '{w['ends'][-45:]}'")
    toward = "SCAM" if gates[name]["expect"] == "LEGITIMATE" else "LEGITIMATE"
    print(f"    lines pushing toward {toward} (the wrong way):")
    wrong_way = infl if toward == "SCAM" else infl[::-1]
    for d, i, line in wrong_way[:8]:
        print(f"      {d:+.4f} [{i:>2}] {line[:95]}")

# ---------------------------------------------------------------------------
print(SEP)
print("F. WHY THE TEMPERATURE CAME OUT AT", round(TEMPERATURE, 3))
m = np.asarray(m_dev, dtype=float)
dev_correct = (m >= 0) == (np.asarray(y_dev) == 1)
test_margin = np.log(np.clip(pt["p"], 1e-6, 1 - 1e-6) / np.clip(1 - pt["p"], 1e-6, 1))
wrong = ~pt["correct"].to_numpy()
out["F_calibration"] = {
    "temperature": TEMPERATURE,
    "dev_accuracy": round(float(dev_correct.mean()), 4),
    "dev_rows": int(len(m)),
    "dev_median_abs_margin": round(float(np.median(np.abs(m))), 3),
    "test_wrong_rows": int(wrong.sum()),
    "test_wrong_median_abs_margin": round(float(np.median(np.abs(test_margin[wrong]))), 3) if wrong.any() else None,
    "test_right_median_abs_margin": round(float(np.median(np.abs(test_margin[~wrong]))), 3),
}
f = out["F_calibration"]
print(f"  dev accuracy {f['dev_accuracy']:.3f} on {f['dev_rows']} rows "
      f"(the set the temperature was fitted on)")
print(f"  test: {f['test_wrong_rows']} wrong rows; median |margin| wrong "
      f"{f['test_wrong_median_abs_margin']} vs right {f['test_right_median_abs_margin']}")
print("  (if dev accuracy is near 1.000, fitting on it pushes the temperature below 1,")
print("   sharpening every score - including any mistakes on new wording)")

# ---------------------------------------------------------------------------
out["pair_test_rows"] = [
    {"pair_id": r.pair_id, "kind": r.kind, "label": r.label, "lang": r.lang,
     "p": round(float(r.p), 4)} for r in pt.itertuples()]
with open("v3_run2_diagnosis.json", "w") as handle:
    json.dump(out, handle, indent=1, ensure_ascii=False)
files.download("v3_run2_diagnosis.json")
print(SEP)
print("saved v3_run2_diagnosis.json - send it together with this printout")
