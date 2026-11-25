"""Regenerate the 15 blind-test transcripts from the case screenshots.

The blind test (2026-10-25/26) sent screenshots only, and the saved API results
keep no chat text. This script runs the project's own OCR code exactly as
POST /ocr does: screenshots_to_conversation(pages in the order sent)["text"].
nlp-service/app/ocr and app/turns.py have not changed since the blind test
(git log: the only later commit on those paths touched app/main.py only).
No model is loaded and no service is called.

Check: each case's message count must equal the count recorded in the blind
test (data/test_real/cases/results.csv, column ocr_messages).

Run with the nlp-service venv, read-only (-B: no bytecode written into the repo):
    nlp-service/.venv/Scripts/python.exe -I -B experiments/scripts/e1_make_transcripts.py

Writes the transcripts (personal data) OUTSIDE the repo:
    ~/rentsafe_experiments_data/blind/blind_transcripts.csv
and a check with no chat text to experiments/results/e1/transcripts_check.json.
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "nlp-service"))
sys.path.insert(0, HERE)

from app.ocr.ocr import screenshots_to_conversation  # noqa: E402
from app.turns import count_messages  # noqa: E402
from common import BLIND_FILE, RESULTS, save_json  # noqa: E402

CASES = os.path.join(REPO, "data", "test_real", "cases")


def main():
    with open(os.path.join(CASES, "results.csv"), encoding="utf-8-sig", newline="") as handle:
        recorded = {r["case_id"]: r for r in csv.DictReader(handle)}
    rows, check = [], []
    for case in sorted(recorded):
        spec = json.load(open(os.path.join(CASES, case, "input.json"), encoding="utf-8-sig"))
        pages = [open(os.path.join(CASES, case, name), "rb").read() for name in spec["pages"]]
        result = screenshots_to_conversation(pages)
        if result["method"] == "bubbles":
            messages = len(result["messages"])
        else:
            messages = count_messages(result["text"])
        label = "SCAM" if spec["truth"].upper() == "SCAM" else "LEGITIMATE"
        rows.append({"case_id": case, "label": label, "origin": spec["origin"], "text": result["text"]})
        want = int(recorded[case]["ocr_messages"] or -1)
        check.append({"case_id": case, "label": label, "origin": spec["origin"], "pages": len(pages),
                      "method": result["method"], "messages": messages, "recorded_messages": want,
                      "match": messages == want, "characters": len(result["text"])})
        print(f"{case}: {len(pages)} pages, {result['method']}, {messages} messages "
              f"(recorded {want}) {'OK' if messages == want else 'MISMATCH'}")
    os.makedirs(os.path.dirname(BLIND_FILE), exist_ok=True)
    with open(BLIND_FILE, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["case_id", "label", "origin", "text"])
        writer.writeheader()
        writer.writerows(rows)
    ok = all(c["match"] for c in check)
    save_json({"all_match": ok, "cases": check}, "e1", "transcripts_check.json")
    print(("ALL 15 MATCH the recorded message counts" if ok else "SOME COUNTS DIFFER")
          + f"\ntranscripts: {BLIND_FILE}")


if __name__ == "__main__":
    main()
