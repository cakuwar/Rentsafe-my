"""Evaluate the image-based bubble segmenter against hand counts.

Two real conversations, both hand counted: a scam from an Android phone (light
theme, 24-hour clock) and a legitimate agent chat from an iPhone (dark theme,
12-hour clock, photo wallpaper). The text-based counter scored 25/25 on the
first and 7/34 on the second.

    python eval/bubble_segmenter_eval.py [--verbose]

Writes eval/results/bubble_segmenter.json.
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

from app.ocr import ocr as ocr_module
from training.redaction import redact_tree
from app.ocr.bubbles import drop_media_text, segment, stitch

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "..", "..", "data", "samples")
OUT = os.path.join(HERE, "results", "bubble_segmenter.json")

CONVERSATIONS = {
    "scam": {"pages": 4, "hand_total": 25},
    "legit": {"pages": 8, "hand_total": 34},
}


def run(verbose=False):
    report = {}
    for name, spec in CONVERSATIONS.items():
        pages = []
        for number in range(1, spec["pages"] + 1):
            image = Image.open(os.path.join(SAMPLES, f"{name}_p{number}.jpg"))
            pages.append(segment(image, ocr_module._preprocess))
        per_page = [[(b.speaker, b.text) for b in page] for page in pages]
        deduped = [f"{speaker}: {text}" for speaker, text in stitch(drop_media_text(pages))]
        total = len(deduped)
        within = abs(total - spec["hand_total"]) <= 2
        report[name] = {
            "hand_total": spec["hand_total"],
            "counted": total,
            "within_2": within,
            "per_page_before_dedupe": [len(p) for p in per_page],
            "messages": deduped,
            "renter_messages": sum(1 for m in deduped if m.startswith("renter:")),
            "owner_messages": sum(1 for m in deduped if m.startswith("owner:")),
        }
        mark = "PASS" if within else "FAIL"
        print(f"{name:<6} counted {total:>3}   hand {spec['hand_total']:>3}   "
              f"{mark}   per page {[len(p) for p in per_page]}   "
              f"renter/owner {report[name]['renter_messages']}/"
              f"{report[name]['owner_messages']}")
        if verbose:
            for index, message in enumerate(deduped, 1):
                print(f"   {index:>3}. {message[:86]}")
            print()

    with io.open(OUT, "w", encoding="utf-8") as handle:
        # Names, addresses and numbers from the screenshots never reach disk.
        json.dump(redact_tree(report), handle, indent=2, ensure_ascii=False)
    return report


if __name__ == "__main__":
    run(verbose="--verbose" in sys.argv)
