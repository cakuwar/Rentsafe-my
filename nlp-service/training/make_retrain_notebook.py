"""Build nlp-service/train_colab_v3.ipynb — the shortcut-fixing retrain."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "train_colab_v3.ipynb")


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code(text):
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
            "source": text.rstrip("\n").splitlines(keepends=True)}


cells = []

cells.append(md("""# RentSafe-MY — XLM-R retrain v3: breaking the price shortcut

Same backbone as the deployed model (`xlm-roberta-base`). What changes is the
**data**, the **context length**, and how the result is **judged**.

## Why the deployed model is wrong

It scored a real, legitimate iBilik agent conversation at **0.9997** — on clean
hand-transcribed text, so OCR is not the cause. Three problems compound:

| problem | evidence |
|---|---|
| **A price shortcut** | Adding ONE line of itemised prices to a known-legitimate chat moves it 0.0006 → **0.9492**. In training, P(SCAM \\| ≥4 RM amounts) = **93.2%**. |
| **Every surface feature was a shortcut** | In the original training set, character count alone predicts the label **77%** of the time; message count 73%; RM amounts 73%. |
| **Train/deploy length mismatch** | Training never exceeded **241 tokens**. The real legitimate conversation is **655–733**, and at 256 the model saw only the first **35–39%** — the part with the price list, not the part with the viewing and key handover. |

## What this notebook does about each

1. **Minimal pairs** (`minimal_pairs_train.csv`, from `training/make_minimal_pairs.py`):
   every legitimate conversation has a scam twin with an identical greeting,
   property details, **price breakdown** and small talk, differing only in the
   mechanics. Price, length and style carry no information, so they cannot be
   learned. Audited before upload: every surface feature now predicts at
   55–58%, against a 55% majority baseline.
2. **512-token context**, and training data long enough to use it: pairs run
   to ~430 tokens, the mechanics sit at a random position rather than always at
   the end, and matched *fragment* pairs start mid-conversation — the shape of
   the second window the service scores on a long chat.
3. **Label smoothing** (0.1), because the old model answered 0.9997 or 0.0021
   and nothing between — no usable gradation of risk.
4. **Acceptance gates** decided *before* training (section 2), scored on the
   real screenshots through the production pipeline.

**Before running: Runtime → Change runtime type → T4 GPU.** Expect ~20–30 min."""))

cells.append(md("## 1. GPU and dependencies"))
cells.append(code('''import torch
print("GPU:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "NONE - switch to T4")'''))
cells.append(code('''!pip install -q "transformers==4.46.2" "accelerate>=0.26.0" scikit-learn'''))

cells.append(md("""## 2. Acceptance criteria — fixed before training

Written down here, before any number exists, so the result is judged by rules
that could not have been chosen to fit it.

A model is **accepted** only if all of these hold:

| # | criterion | why |
|---|---|---|
| A1 | original validation macro-F1 ≥ **0.90** | fixing the shortcut must not break what already worked |
| A2 | minimal-pair test: **pair accuracy ≥ 0.85** — both twins of a `pair_id` right, on pairs whose mechanic sentences never appear in training (held-out family) | the direct test of reading mechanics rather than surface or memorised sentences |
| A3 | gate `real_legit_production` → LEGITIMATE | the failure that started this |
| A4 | gate `real_scam_production` → SCAM | must not fix A3 by going soft on scams |
| A5 | gates `shortcut_plus_prices*` → LEGITIMATE | the shortcut itself |
| A6 | gate `ablation_mechanics_removed` → LEGITIMATE | a scam with the scam removed must stop scoring as one |
| A7 | fewer than **50%** of validation predictions saturated (>0.99 or <0.01), raw output | sanity check that label smoothing took effect — **not** evidence of calibration, see below |

**A7 is effectively guaranteed by label smoothing 0.1, so it is not evidence of
calibration.** Smoothing makes the training target 0.95 / 0.05 instead of 1 / 0,
so the loss is minimised by predicting about 0.95 — below the 0.99 line A7 calls
saturated. Once smoothing is on, A7 passes almost regardless of how good or how
calibrated the model is; it only confirms smoothing took effect. The evidence of
calibration is the out-of-sample ECE and Brier score on the held-out pair test
after temperature scaling (section 6), which are reported, not gated.

**What A2 measures.** Test pairs use a held-out *family* of mechanic phrasings:
the same tactics (viewing refused, pay first, keys by courier, urgency, a third
party's account, and their legitimate counterparts) in sentences that never
occur in training — section 4 checks this before training starts. The shared
scaffolding (greeting, prices, terms, small talk) is common to both families; it
is identical in both twins and carries no label. So A2 tests reading a *known
tactic in new words*, not recognising a *new tactic*.

**Changed after run 1 — the criteria above were not.** Run 1 was not accepted
(A3 0.7811, A6 0.5219; `eval/results/v3_run1_printout.txt`). Its diagnosis
found the first window of the real legitimate OCR text ending mid-sentence, and
that a window with no scam behaviour in it scored 0.8–0.9 because training never
said what such a window is. Two changes follow, both general rather than fitted
to that chat: windows are now cut only between messages (section 6, identical to
the service), and the training pairs add *prefix* rows (text before the twins
diverge → LEGITIMATE), length-matched *core* rows (→ SCAM) and *truncated*
pairs. Both were chosen after seeing run 1 fail on these gates, so a pass on A3
and A6 in this run is weaker evidence than it would have been in run 1.

**What passing does NOT prove.** The real legitimate conversation was used to
diagnose this problem and the training data was designed knowing how it failed;
the real scam's text was used to write layer 1's rules; the minimal-pair test
comes from the same generator, scaffolding and tactics as the training pairs.
Passing is necessary. It is not independent evidence of real-world accuracy. Only conversations in
`data/test_real/` — collected after this and never used for anything else — can
provide that."""))

cells.append(code('''CRITERIA = {
    "val_macro_f1_min": 0.90,
    "pair_accuracy_min": 0.85,
    "must_pass_gates": [
        "real_legit_production",
        "real_scam_production",
        "shortcut_plus_prices",
        "shortcut_plus_prices_terms",
        "ablation_mechanics_removed",
    ],
    "max_saturated_share": 0.50,
}
print("criteria fixed:", CRITERIA)'''))

cells.append(md("""## 3. Upload the data

**Upload one file: `nlp-service/colab_upload_v3.zip`.** It holds all five
inputs plus a manifest, and is built by `python training/pack_for_colab.py`.

Colab's file picker selects from **one folder at a time**, and the five files
live in three folders, so choosing them individually only ever sends some of
them. The zip avoids that. Loose files still work: the cell keeps asking until
all five are present.

| inside the zip | built from |
|---|---|
| `train.csv`, `val.csv` | `data/processed/random/` |
| `minimal_pairs_train.csv`, `minimal_pairs_test.csv` | `data/processed/augmented/` |
| `gates.json` | `nlp-service/training/` (already redacted) |

Nothing from `data/samples/` or `data/test_real/` is uploaded."""))

cells.append(code('''import hashlib
import json
import os
import re
import zipfile

from google.colab import files

REQUIRED = ["train.csv", "val.csv", "minimal_pairs_train.csv",
            "minimal_pairs_test.csv", "gates.json"]
os.makedirs("data", exist_ok=True)


def missing():
    return [n for n in REQUIRED if not os.path.exists(os.path.join("data", n))]


def take(name):
    # Colab saves a re-uploaded file as "x (1).csv"; store it under its real name.
    clean = re.sub(r" \\(\\d+\\)(?=\\.\\w+$)", "", name)
    if clean.endswith(".zip"):
        with zipfile.ZipFile(name) as bundle:
            bundle.extractall("data")
        os.remove(name)
        print(f"  unpacked {name}")
    else:
        os.replace(name, os.path.join("data", clean))
        print(f"  saved {clean}")


for attempt in range(5):
    if not missing():
        break
    print("Still needed:", ", ".join(missing()))
    print("Easiest: upload colab_upload_v3.zip from nlp-service/ (one file).")
    for name in files.upload():
        take(name)

assert not missing(), f"still missing: {missing()} - run this cell again"

# From the zip, every file must be byte-identical to what was packed, so an old
# copy of a file cannot slip in beside new ones.
manifest_path = os.path.join("data", "manifest.json")
if os.path.exists(manifest_path):
    manifest = json.load(open(manifest_path))
    for name, expected in manifest["files"].items():
        with open(os.path.join("data", name), "rb") as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        assert digest == expected["sha256"], f"{name} does not match the zip's manifest"
    print(f"verified against the manifest (packed {manifest['packed']})")
else:
    print("loose files - no manifest to verify against")

for name in REQUIRED:
    print(f"  {name:<26} {os.path.getsize(os.path.join('data', name)):>8} bytes")
print("all five files present")'''))

cells.append(md("""## 4. Confirm the uploaded data is the fixed version

A cheap check that the shortcut really is gone from what is about to be trained
on. If P(SCAM | ≥4 RM amounts) is still near 93%, the wrong files were
uploaded — stop."""))

cells.append(code('''import re
import numpy as np
import pandas as pd

LABELS = {"LEGITIMATE": 0, "SCAM": 1}
AMOUNT = re.compile(r"\\brm\\s?\\d", re.I)


def load(path):
    frame = pd.read_csv(path)
    frame["label"] = frame["label"].str.upper().replace({"LEGIT": "LEGITIMATE"})
    return frame


original = load("data/train.csv")
pairs = load("data/minimal_pairs_train.csv")
val = load("data/val.csv")
pair_test = load("data/minimal_pairs_test.csv")

# Hold out ~10% of the training PAIRS for model selection, so the pair test
# split is never used to choose a checkpoint.
groups = sorted(pairs["source_group"].unique())
rng = np.random.default_rng(42)
dev_groups = set(rng.choice(groups, size=max(1, len(groups) // 10), replace=False))
pair_dev = pairs[pairs["source_group"].isin(dev_groups)]
pair_train = pairs[~pairs["source_group"].isin(dev_groups)]

# A pair_id is one twin pair (one legitimate, one scam); source_group is the
# parent pair, shared with its fragment pair so the dev split keeps them together.
# Twin kinds hold one legitimate + one scam row per pair_id. A "prefix" is one
# LEGITIMATE row of text both twins share (no scam behaviour yet); its "core" is
# one SCAM row of the same length that includes a scam line.
TWIN_KINDS = ["full", "fragment", "truncated"]
for name, frame in (("minimal_pairs_train", pairs), ("minimal_pairs_test", pair_test)):
    assert {"pair_id", "family", "kind"} <= set(frame.columns), (
        f"{name}.csv is an old version - rebuild colab_upload_v3.zip")
    assert {"prefix", "core", "truncated"} <= set(frame["kind"]), (
        f"{name}.csv has no prefix/core/truncated rows - rebuild colab_upload_v3.zip")
    twin_rows = frame[frame["kind"].isin(TWIN_KINDS)]
    twins = twin_rows.groupby("pair_id")["label"].agg(lambda l: tuple(sorted(l)))
    assert all(t == ("LEGITIMATE", "SCAM") for t in twins), (
        f"{name}: some pair_id is not exactly one legitimate + one scam twin")
    assert (frame.loc[frame["kind"] == "prefix", "label"] == "LEGITIMATE").all()
    assert (frame.loc[frame["kind"] == "core", "label"] == "SCAM").all()
assert set(pairs["family"]) == {"train"}, "training pairs must all be the train family"
assert set(pair_test["family"]) == {"heldout"}, "test pairs must all be the held-out family"


def _mechanics(frame):
    lines = set()
    for _, grp in frame[frame["kind"].isin(TWIN_KINDS)].groupby("pair_id"):
        legit = grp.loc[grp["label"] == "LEGITIMATE", "text"].iloc[0].split("\\n")
        scam = grp.loc[grp["label"] == "SCAM", "text"].iloc[0].split("\\n")
        lines.update(l.split(": ", 1)[-1] for a, b in zip(legit, scam) if a != b for l in (a, b))
    return lines


train_lines = {l.split(": ", 1)[-1] for t in pairs["text"] for l in t.split("\\n")}
test_mechanics = _mechanics(pair_test)
seen = test_mechanics & train_lines
assert not seen, f"{len(seen)} test mechanic sentences also occur in training"
full_pairs = pair_test.loc[pair_test["kind"] == "full", "pair_id"].nunique()
print(f"pair test: {full_pairs} pairs + {len(pair_test) - 2 * full_pairs} derived rows, "
      f"held-out family; {len(test_mechanics)} mechanic sentences, 0 seen in training")

train = pd.concat([original[["text", "label"]], pair_train[["text", "label"]]],
                  ignore_index=True).sample(frac=1, random_state=42)
dev = pd.concat([val[["text", "label"]], pair_dev[["text", "label"]]],
                ignore_index=True)

amounts = train["text"].apply(lambda t: len(AMOUNT.findall(str(t))))
share = (train.loc[amounts >= 4, "label"] == "SCAM").mean()
print(f"train {len(train)} rows  ({(train.label=='SCAM').sum()} scam / "
      f"{(train.label=='LEGITIMATE').sum()} legit)")
print(f"dev   {len(dev)} rows   (original val + held-out pairs)")
print(f"P(SCAM | >= 4 RM amounts) in train: {share:.1%}   (was 93.2% before)")
assert share < 0.70, "shortcut still present - check you uploaded the regenerated files"'''))

cells.append(md("""## 5. Train

`xlm-roberta-base`, 512 tokens, class-weighted loss with **label smoothing
0.1**, early stopping on dev macro-F1. The dev set mixes the original
validation data with held-out minimal pairs, so the checkpoint is chosen for
reading mechanics *and* not regressing — not for either alone."""))

cells.append(code('''from sklearn.metrics import (accuracy_score, f1_score, matthews_corrcoef,
                             precision_recall_fscore_support)
from transformers import (AutoModelForSequenceClassification, AutoTokenizer,
                          DataCollatorWithPadding, EarlyStoppingCallback, Trainer,
                          TrainingArguments, set_seed)

MODEL = "xlm-roberta-base"
MAX_LENGTH = 512
LABEL_SMOOTHING = 0.1
OUT_DIR = "xlm-roberta-scam-v3"
set_seed(42)

tokenizer = AutoTokenizer.from_pretrained(MODEL)


class Rows(torch.utils.data.Dataset):
    def __init__(self, frame):
        self.enc = tokenizer(frame["text"].tolist(), truncation=True,
                             max_length=MAX_LENGTH)
        self.labels = [LABELS[l] for l in frame["label"]]

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, i):
        item = {k: v[i] for k, v in self.enc.items()}
        item["labels"] = self.labels[i]
        return item


counts = train["label"].value_counts()
weights = torch.tensor([len(train) / (2 * counts[n]) for n in ("LEGITIMATE", "SCAM")],
                       dtype=torch.float)


class WeightedSmoothedTrainer(Trainer):
    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.pop("labels")
        outputs = model(**inputs)
        loss = torch.nn.functional.cross_entropy(
            outputs.logits, labels, weight=weights.to(outputs.logits.device),
            label_smoothing=LABEL_SMOOTHING,
        )
        return (loss, outputs) if return_outputs else loss


def metrics(prediction):
    predicted = np.argmax(prediction.predictions, axis=1)
    labels = prediction.label_ids
    return {
        "accuracy": accuracy_score(labels, predicted),
        "macro_f1": f1_score(labels, predicted, average="macro"),
        "mcc": matthews_corrcoef(labels, predicted),
    }


model = AutoModelForSequenceClassification.from_pretrained(
    MODEL, num_labels=2, id2label={0: "LEGITIMATE", 1: "SCAM"}, label2id=LABELS)

args = TrainingArguments(
    output_dir="checkpoints-v3",
    num_train_epochs=8,
    per_device_train_batch_size=8,
    gradient_accumulation_steps=2,
    per_device_eval_batch_size=16,
    learning_rate=2e-5,
    warmup_ratio=0.1,
    weight_decay=0.01,
    fp16=torch.cuda.is_available(),
    eval_strategy="epoch",
    save_strategy="epoch",
    save_total_limit=1,
    load_best_model_at_end=True,
    metric_for_best_model="macro_f1",
    greater_is_better=True,
    logging_steps=20,
    seed=42,
    report_to="none",
)

trainer = WeightedSmoothedTrainer(
    model=model, args=args,
    train_dataset=Rows(train), eval_dataset=Rows(dev),
    processing_class=tokenizer,
    data_collator=DataCollatorWithPadding(tokenizer),
    compute_metrics=metrics,
    callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
)
trainer.train()'''))

cells.append(md("""## 6. Evaluate against the criteria

Long conversations are scored in **windows of up to 512 tokens cut between
messages, never inside one**, about 256 tokens apart, taking the maximum — the
same function the service uses (`tests/test_notebook_parity.py` checks they
agree). Run 1 cut at fixed token offsets, and its first window on the real
legitimate chat ended mid-sentence.

**Calibration.** Label smoothing stops the model being pushed to 0 and 1, but
does not make its 0.8 mean "right 80% of the time". A single temperature is
fitted on the dev set after training and saved into the checkpoint's
`config.json`; the service divides logits by it. It cannot change any verdict —
a score never crosses 0.5 because of it — so criteria A1–A6 are unaffected. A7
is judged on the raw output, which the temperature cannot game. The calibrated
error is measured on the minimal-pair test split, which the temperature never
saw."""))

cells.append(code('''import json

best = trainer.model.eval()
device = best.device
scam_index, legit_index = LABELS["SCAM"], LABELS["LEGITIMATE"]


STRIDE = 256


def message_windows(text):
    """Token ids of each window, cut only between messages (lines).

    Identical to app/layer2/classifier.py::_message_windows, which
    tests/test_notebook_parity.py checks: whole messages packed into
    MAX_LENGTH - 2 tokens, the next window about STRIDE tokens later on a
    message boundary with no gap, the last window packed back from the end,
    and only a single over-long message ever cut.
    """
    body = MAX_LENGTH - 2
    ids = [tokenizer(line, add_special_tokens=False)["input_ids"]
           for line in text.split("\\n") if line.strip()]
    if not ids:
        return [[]]
    offsets = [0]
    for message in ids:
        offsets.append(offsets[-1] + len(message))
    last = len(ids) - 1

    def pack(first):
        end, total = first, len(ids[first])
        while end < last and total + len(ids[end + 1]) <= body:
            end += 1
            total += len(ids[end])
        return end

    spans, first = [], 0
    while True:
        if len(ids[first]) > body:
            spans.append((first, first))
            end = first
        else:
            end = pack(first)
            spans.append((first, end))
        if end >= last:
            break
        target = offsets[first] + STRIDE
        following = next((i for i in range(first + 1, end + 1) if offsets[i] >= target), end + 1)
        first = min(following, end + 1)

    if len(ids[last]) <= body:
        start, total = last, len(ids[last])
        while start > 0 and total + len(ids[start - 1]) <= body:
            start -= 1
            total += len(ids[start])
        if start < spans[-1][0]:
            spans[-1] = (start, last)

    windows = []
    for first, end in spans:
        tokens = [token for message in ids[first:end + 1] for token in message]
        if len(tokens) <= body:
            windows.append(tokens)
        else:
            starts = list(range(0, len(tokens) - body + 1, STRIDE))
            if starts[-1] + body < len(tokens):
                starts.append(len(tokens) - body)
            windows += [tokens[s:s + body] for s in starts]
    return windows


def windowed_margin(text):
    """Highest SCAM-minus-LEGITIMATE logit over the service's windows.

    For two classes, softmax(logits / T)[SCAM] = sigmoid(margin / T), so the
    service's "highest window probability" is sigmoid(max margin / T) - one
    forward pass serves both the raw and the calibrated score.
    """
    margins = []
    with torch.no_grad():
        for window in message_windows(text):
            enc = tokenizer.prepare_for_model(window, add_special_tokens=True,
                                              return_tensors="pt")
            enc = {k: (v.unsqueeze(0) if v.dim() == 1 else v).to(device)
                   for k, v in enc.items()}
            logits = best(**enc).logits[0].float()
            margins.append(float(logits[scam_index] - logits[legit_index]))
    return max(margins)


def probability(margins, temperature=1.0):
    return 1.0 / (1.0 + np.exp(-np.asarray(margins, dtype=float) / temperature))


def score_frame(frame):
    return np.array([windowed_margin(t) for t in frame["text"]])


def ece(p, y, n_bins=10):
    bins = np.linspace(0, 1, n_bins + 1)
    total = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (p >= lo) & (p < hi) if hi < 1 else (p >= lo)
        if mask.any():
            total += mask.mean() * abs(p[mask].mean() - y[mask].mean())
    return float(total)


def fit_temperature(margins, labels):
    """One scalar T minimising log-loss on held-out data (temperature scaling).
    Clamped to the range the service accepts."""
    m = torch.tensor(margins, dtype=torch.float)
    y = torch.tensor(labels, dtype=torch.float)
    log_t = torch.zeros(1, requires_grad=True)
    optimiser = torch.optim.LBFGS([log_t], lr=0.1, max_iter=200)

    def closure():
        optimiser.zero_grad()
        loss = torch.nn.functional.binary_cross_entropy_with_logits(m / log_t.exp(), y)
        loss.backward()
        return loss

    optimiser.step(closure)
    return float(log_t.detach().exp().clamp(0.05, 20.0))


report = {}

# Calibration temperature, fitted on the dev set (original validation +
# held-out training pairs) - never on the minimal-pair TEST split, so the
# calibrated error measured there below is out of sample.
m_dev = score_frame(dev)
y_dev = np.array([LABELS[l] for l in dev["label"]])
TEMPERATURE = fit_temperature(m_dev, y_dev)

# A1 + A7: original validation. Verdicts are identical at any temperature.
m_val = score_frame(val)
y_val = np.array([LABELS[l] for l in val["label"]])
p_val = probability(m_val)
p_val_cal = probability(m_val, TEMPERATURE)
pred_val = (p_val >= 0.5).astype(int)
report["val"] = {
    "accuracy": float(accuracy_score(y_val, pred_val)),
    "macro_f1": float(f1_score(y_val, pred_val, average="macro")),
    "mcc": float(matthews_corrcoef(y_val, pred_val)),
    "saturated_share": float(((p_val > 0.99) | (p_val < 0.01)).mean()),
    "ece": ece(p_val, y_val),
    "brier": float(((p_val - y_val) ** 2).mean()),
}

# A2: unseen minimal pairs
m_pairs = score_frame(pair_test)
p_pairs = probability(m_pairs)
y_pairs = pair_test["label"].map(LABELS).to_numpy()
pair_test = pair_test.assign(p=p_pairs,
                             correct=((p_pairs >= 0.5).astype(int) == y_pairs))
# A2 is judged on whole conversations. Fragment pairs (mid-conversation cuts of
# the same pair, the shape of a later window) are reported alongside.
kind = pair_test["kind"] if "kind" in pair_test else pd.Series("full", index=pair_test.index)
full, fragments = pair_test[kind == "full"], pair_test[kind == "fragment"]
pair_ok = full.groupby("pair_id")["correct"].all()
report["pairs"] = {
    "row_accuracy": float(full["correct"].mean()),
    "pair_accuracy": float(pair_ok.mean()),
    "pairs": int(len(pair_ok)),
}
if len(fragments):
    fragment_ok = fragments.groupby("pair_id")["correct"].all()
    report["pairs"]["fragment_pair_accuracy"] = float(fragment_ok.mean())
    report["pairs"]["fragment_pairs"] = int(len(fragment_ok))
truncated = pair_test[kind == "truncated"]
if len(truncated):
    report["pairs"]["truncated_pair_accuracy"] = float(
        truncated.groupby("pair_id")["correct"].all().mean())
# Window-level meaning: text with no scam behaviour must score LEGITIMATE, and
# the same number of lines holding a scam line must score SCAM.
for single in ("prefix", "core"):
    rows = pair_test[kind == single]
    if len(rows):
        report["pairs"][f"{single}_accuracy"] = float(rows["correct"].mean())
        report["pairs"][f"{single}_rows"] = int(len(rows))

p_pairs_cal = probability(m_pairs, TEMPERATURE)
report["calibration"] = {
    "temperature": TEMPERATURE,
    "fitted_on": "dev (original validation + held-out training pairs)",
    "pair_test_ece_raw": ece(p_pairs, y_pairs),
    "pair_test_ece_calibrated": ece(p_pairs_cal, y_pairs),
    "pair_test_brier_raw": float(((p_pairs - y_pairs) ** 2).mean()),
    "pair_test_brier_calibrated": float(((p_pairs_cal - y_pairs) ** 2).mean()),
    "val_ece_calibrated_in_sample": ece(p_val_cal, y_val),
    "val_saturated_share_calibrated":
        float(((p_val_cal > 0.99) | (p_val_cal < 0.01)).mean()),
}

# A3-A6: gates
gates = json.load(open("data/gates.json", encoding="utf-8"))
report["gates"] = {}
for name, gate in gates.items():
    if name.startswith("_"):
        continue
    margin = windowed_margin(gate["text"])
    p = float(probability(margin))
    got = "SCAM" if p >= 0.5 else "LEGITIMATE"
    report["gates"][name] = {
        "expect": gate["expect"], "p_scam": round(p, 4),
        "p_scam_calibrated": round(float(probability(margin, TEMPERATURE)), 4),
        "passed": got == gate["expect"],
    }

print("VALIDATION")
for k, v in report["val"].items():
    print(f"  {k:<16} {v:.4f}")
print(f"\\nMINIMAL PAIRS (unseen, {report['pairs']['pairs']} pairs)")
print(f"  row accuracy   {report['pairs']['row_accuracy']:.4f}")
print(f"  pair accuracy  {report['pairs']['pair_accuracy']:.4f}   (both twins right)")
if "fragment_pair_accuracy" in report["pairs"]:
    print(f"  fragment pairs {report['pairs']['fragment_pair_accuracy']:.4f}   "
          f"({report['pairs']['fragment_pairs']} pairs cut mid-conversation; reported, not gated)")
if "truncated_pair_accuracy" in report["pairs"]:
    print(f"  truncated pairs {report['pairs']['truncated_pair_accuracy']:.4f}  (cut before the goodbye; reported)")
for single, what in (("prefix", "no scam behaviour -> LEGITIMATE"),
                     ("core", "same length with a scam line -> SCAM")):
    if f"{single}_accuracy" in report["pairs"]:
        print(f"  {single:<6} rows    {report['pairs'][f'{single}_accuracy']:.4f}   "
              f"({report['pairs'][f'{single}_rows']} rows, {what}; reported, not gated)")
c = report["calibration"]
print(f"\\nCALIBRATION  temperature {c['temperature']:.3f}")
print(f"  pair-test ECE    raw {c['pair_test_ece_raw']:.4f}  ->  calibrated "
      f"{c['pair_test_ece_calibrated']:.4f}   (out of sample)")
print(f"  pair-test Brier  raw {c['pair_test_brier_raw']:.4f}  ->  calibrated "
      f"{c['pair_test_brier_calibrated']:.4f}")
print("\\nGATES                          expect     p(scam)  calibrated  result")
for name, g in report["gates"].items():
    print(f"  {name:<28} {g['expect']:<10} {g['p_scam']:>7.4f}  {g['p_scam_calibrated']:>10.4f}  "
          f"{'PASS' if g['passed'] else 'FAIL'}")'''))

cells.append(md("## 7. Verdict"))

cells.append(code('''checks = {
    "A1 val macro-F1 >= 0.90":
        report["val"]["macro_f1"] >= CRITERIA["val_macro_f1_min"],
    "A2 pair accuracy >= 0.85":
        report["pairs"]["pair_accuracy"] >= CRITERIA["pair_accuracy_min"],
    "A7 saturated share < 0.50":
        report["val"]["saturated_share"] < CRITERIA["max_saturated_share"],
}
for gate in CRITERIA["must_pass_gates"]:
    checks[f"gate {gate}"] = report["gates"][gate]["passed"]

for name, ok in checks.items():
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")

accepted = all(checks.values())
report["accepted"] = accepted
report["checks"] = checks
print()
print("ACCEPTED - download and deploy (section 8)." if accepted else
      "NOT ACCEPTED - do not deploy. Send the printout above; the failing "
      "criterion says what to change.")'''))

cells.append(md("""## 8. Save and download

Saved as `xlm-roberta-scam-v3` — a **new** folder, so the deployed model is not
overwritten. Download both the zip and `v3_report.json`; the report is the
evidence for the write-up."""))

cells.append(code('''import shutil

# The service reads this and divides logits by it (app/layer2/classifier.py).
# Not "temperature": that name is a text-generation setting in HF configs.
best.config.calibration_temperature = TEMPERATURE
trainer.save_model(OUT_DIR)
tokenizer.save_pretrained(OUT_DIR)
saved = json.load(open(os.path.join(OUT_DIR, "config.json")))
assert abs(saved["calibration_temperature"] - TEMPERATURE) < 1e-9, "temperature not saved"
print(f"calibration_temperature {TEMPERATURE:.3f} saved in config.json")
with open("v3_report.json", "w") as handle:
    json.dump(report, handle, indent=2)

archive = shutil.make_archive(OUT_DIR, "zip", OUT_DIR)
print(f"{os.path.getsize(archive)/1e6:.0f} MB")
files.download("v3_report.json")
files.download(archive)'''))

cells.append(md("""## 9. After download

1. Send `v3_report.json`.
2. If **accepted**: unzip to `nlp-service/models/xlm-roberta-scam-v3/` and change
   one line in `nlp-service/.env`:
   ```
   FINETUNED_MODEL_DIR=./models/xlm-roberta-scam-v3
   ```
   `PRIMARY_MODEL` stays `xlm-roberta-base`. Keep the old folder for rollback.
3. Then re-run the truncation sweep (`eval/truncation_sweep.py`): the short-input
   guard's threshold was measured on the old model and must be re-derived for the
   new one.
4. The honest test: put real conversations the project has never used into
   `data/test_real/` and run `eval/test_real.py`. Until that exists, no number
   here is evidence of real-world accuracy."""))

notebook = {
    "nbformat": 4, "nbformat_minor": 0,
    "metadata": {"colab": {"provenance": [], "gpuType": "T4"},
                 "kernelspec": {"display_name": "Python 3", "name": "python3"},
                 "language_info": {"name": "python"}, "accelerator": "GPU"},
    "cells": cells,
}
with open(OUT, "w", encoding="utf-8", newline="\n") as handle:
    json.dump(notebook, handle, indent=1, ensure_ascii=False)
    handle.write("\n")
print("wrote", OUT, len(cells), "cells")
