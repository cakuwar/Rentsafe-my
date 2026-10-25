"""Fine-tune a transformer for binary scam classification (FYP1 — P4).

Reads the labelled dataset (data/processed/train.csv, val.csv with columns:
text,label where label in {SCAM, LEGITIMATE}), fine-tunes config.PRIMARY_MODEL,
and saves weights to config.FINETUNED_MODEL_DIR. Target: validation F1 >= 0.80.

Run from the nlp-service directory once you have a labelled dataset:
    python scripts_train.py --data ../data/processed --epochs 4
"""
import argparse
import os
import numpy as np
import pandas as pd
from datasets import Dataset
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)
from app import config

LABELS = {"LEGITIMATE": 0, "SCAM": 1}


def load_split(path):
    frame = pd.read_csv(path)
    frame["label"] = frame["label"].str.upper().replace({"LEGIT": "LEGITIMATE"})
    invalid = sorted(set(frame["label"]) - set(LABELS))
    if invalid:
        raise ValueError(f"Unsupported labels in {path}: {invalid}")
    return Dataset.from_pandas(
        frame[["text", "label"]].assign(label=frame["label"].map(LABELS)),
        preserve_index=False,
    )


def compute_metrics(prediction):
    predicted = np.argmax(prediction.predictions, axis=1)
    precision, recall, f1, _ = precision_recall_fscore_support(
        prediction.label_ids,
        predicted,
        average="binary",
        zero_division=0,
    )
    return {
        "accuracy": accuracy_score(prediction.label_ids, predicted),
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="../data/processed")
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--out", default=config.FINETUNED_MODEL_DIR)
    args = ap.parse_args()

    train = load_split(os.path.join(args.data, "train.csv"))
    validation = load_split(os.path.join(args.data, "val.csv"))
    tokenizer = AutoTokenizer.from_pretrained(config.PRIMARY_MODEL)

    def tokenize(batch):
        return tokenizer(batch["text"], truncation=True, max_length=192)

    train = train.map(tokenize, batched=True)
    validation = validation.map(tokenize, batched=True)
    model = AutoModelForSequenceClassification.from_pretrained(
        config.PRIMARY_MODEL,
        num_labels=2,
        id2label={0: "LEGITIMATE", 1: "SCAM"},
        label2id=LABELS,
    )
    training_args = TrainingArguments(
        output_dir=args.out,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=8,
        per_device_eval_batch_size=8,
        optim="adafactor",
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        report_to="none",
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train,
        eval_dataset=validation,
        tokenizer=tokenizer,
        compute_metrics=compute_metrics,
    )
    trainer.train()
    trainer.save_model(args.out)
    tokenizer.save_pretrained(args.out)


if __name__ == "__main__":
    main()
