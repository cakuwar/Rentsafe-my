"""Merge raw + synthetic examples into train/val/test CSVs (FYP1 — P2/P4).

Reads .txt files from data/raw/scam, data/raw/legitimate, data/synthetic
(one example per file, or one per line for .jsonl), assigns labels, holds out a
fixed test set, and writes data/processed/{train,val,test}.csv.

Usage:  python scripts/build_dataset.py
"""
import csv
import glob
import os
import random

random.seed(42)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
SYN = os.path.join(ROOT, "data", "synthetic")
OUT = os.path.join(ROOT, "data", "processed")

HELD_OUT_TEST_SCAM = 20  # never train on these


def load_dir(path, label, origin):
    rows = []
    for fp in glob.glob(os.path.join(path, "*.txt")):
        with open(fp, encoding="utf-8") as f:
            text = f.read().strip()
        if text:
            rows.append({"text": text, "label": label, "origin": origin, "source": os.path.basename(fp)})
    return rows


def normalise_label(label):
    label = str(label).strip().upper()
    if label == "LEGIT":
        return "LEGITIMATE"
    if label in {"SCAM", "LEGITIMATE"}:
        return label
    return None


def load_csv_dir(path, origin):
    rows = []
    for fp in glob.glob(os.path.join(path, "*.csv")):
        with open(fp, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for item in reader:
                text = (item.get("text") or item.get("conversation_text") or "").strip()
                label = normalise_label(item.get("label", ""))
                if not text or label is None:
                    continue
                rows.append({
                    "text": text,
                    "label": label,
                    "origin": origin,
                    "source": item.get("source_reference") or os.path.basename(fp),
                })
    return rows


def load_csv_file(path, origin):
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for item in reader:
            text = (item.get("text") or item.get("conversation_text") or "").strip()
            label = normalise_label(item.get("label", ""))
            if not text or label is None:
                continue
            rows.append({
                "text": text,
                "label": label,
                "origin": item.get("origin") or origin,
                "source": item.get("source") or os.path.basename(path),
            })
    return rows


def split_rows(rows, split_name):
    return [{**row, "split": split_name} for row in rows]


def main():
    existing_test = []
    test_path = os.path.join(OUT, "test.csv")
    if os.path.isfile(test_path):
        existing_test = load_csv_file(test_path, "real")

    scam = load_dir(os.path.join(RAW, "scam"), "SCAM", "real")
    legit = load_dir(os.path.join(RAW, "legitimate"), "LEGITIMATE", "real")
    raw_csv = load_csv_dir(RAW, "real")
    syn = load_dir(SYN, "SCAM", "synthetic")
    syn_csv = load_csv_dir(SYN, "synthetic")

    scam.extend(row for row in raw_csv if row["label"] == "SCAM")
    legit.extend(row for row in raw_csv if row["label"] == "LEGITIMATE")
    synthetic_scam = syn + [row for row in syn_csv if row["label"] == "SCAM"]
    synthetic_legit = [row for row in syn_csv if row["label"] == "LEGITIMATE"]

    all_rows = scam + legit + synthetic_scam + synthetic_legit
    test_texts = {row["text"] for row in existing_test}
    train_pool = [row for row in all_rows if row["text"] not in test_texts]

    if existing_test:
        test = split_rows(existing_test, "test")
    else:
        all_scam = scam + synthetic_scam
        random.shuffle(all_scam)
        held_out = min(HELD_OUT_TEST_SCAM, len(all_scam))
        test = split_rows(all_scam[:held_out], "test")
        held_out_texts = {row["text"] for row in test}
        train_pool = [row for row in all_rows if row["text"] not in held_out_texts]

    random.shuffle(train_pool)

    n_val = max(1, int(len(train_pool) * 0.15))
    val = split_rows(train_pool[:n_val], "val")
    train = split_rows(train_pool[n_val:], "train")

    os.makedirs(OUT, exist_ok=True)
    for name, rows in [("train", train), ("val", val), ("test", test)]:
        with open(os.path.join(OUT, f"{name}.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["text", "label", "origin", "source", "split"])
            w.writeheader()
            w.writerows(rows)
        print(f"{name}: {len(rows)} examples")


if __name__ == "__main__":
    main()
