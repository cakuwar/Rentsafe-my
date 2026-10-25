"""Prototype: segment chat bubbles by layout instead of by parsing text.

The text-based counter picks a strategy by counting timestamp-like lines, which
flipped between 76 and 7 on one iOS conversation. Layout does not depend on
reading the clock at all: a bubble is a block of text on one side of the
screen, separated from the next by a vertical gap or a change of side.

Side also gives speaker attribution for free — incoming bubbles sit at the left
margin, outgoing ones do not — which OCR text alone has no way to recover.

    python eval/segmenter_probe.py

Compares stitched totals to hand counts for both real conversations.
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytesseract
from PIL import Image

from app.ocr import ocr as ocr_module
from training.redaction import redact_tree

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "..", "..", "data", "samples")
OUT = os.path.join(HERE, "results", "segmenter_probe.json")

HAND_TOTAL = {"scam": 25, "legit": 34}


def lines_of(image):
    """Text lines with their bounding boxes, from Tesseract's layout analysis."""
    processed = ocr_module._preprocess(image)
    data = pytesseract.image_to_data(
        processed, lang="eng+msa", config="--psm 3",
        output_type=pytesseract.Output.DICT,
    )
    lines = {}
    for i, word in enumerate(data["text"]):
        if not word.strip() or float(data["conf"][i]) < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        line = lines.setdefault(key, {
            "words": [], "left": 10**9, "right": 0, "top": 10**9, "bottom": 0,
        })
        line["words"].append(word)
        line["left"] = min(line["left"], data["left"][i])
        line["right"] = max(line["right"], data["left"][i] + data["width"][i])
        line["top"] = min(line["top"], data["top"][i])
        line["bottom"] = max(line["bottom"], data["top"][i] + data["height"][i])
    result = []
    for line in lines.values():
        line["text"] = " ".join(line["words"])
        result.append(line)
    return sorted(result, key=lambda l: l["top"])


def segment(image, gap_factor=1.6, margin_frac=0.12, header_frac=0.11,
            footer_frac=0.085):
    width, height = image.size
    lines = lines_of(image)

    # Phone chrome sits at fixed screen positions on every screenshot: the
    # status bar and contact header at the top, the input bar at the bottom.
    body = [
        l for l in lines
        if l["top"] > height * header_frac and l["bottom"] < height * (1 - footer_frac)
    ]
    if not body:
        return []

    heights = sorted(l["bottom"] - l["top"] for l in body)
    line_h = max(8, heights[len(heights) // 2])

    bubbles = []
    for line in body:
        side = "owner" if line["left"] < width * margin_frac else "renter"
        if bubbles:
            last = bubbles[-1]
            gap = line["top"] - last["bottom"]
            if last["side"] == side and gap < line_h * gap_factor:
                last["lines"].append(line["text"])
                last["bottom"] = line["bottom"]
                continue
        bubbles.append({"side": side, "lines": [line["text"]],
                        "top": line["top"], "bottom": line["bottom"]})
    return bubbles


def main():
    report = {}
    for convo, n in (("scam", 4), ("legit", 8)):
        per_page = []
        for page in range(1, n + 1):
            path = os.path.join(SAMPLES, f"{convo}_p{page}.jpg")
            image = Image.open(path)
            bubbles = segment(image)
            per_page.append({"page": page, "bubbles": len(bubbles),
                             "sides": [b["side"] for b in bubbles],
                             "text": [" ".join(b["lines"])[:80] for b in bubbles]})
        total = sum(p["bubbles"] for p in per_page)
        report[convo] = {"hand_total": HAND_TOTAL[convo],
                         "sum_of_pages": total, "per_page": per_page}
        print(f"{convo}: sum of per-page bubbles {total}  (hand, de-duplicated: "
              f"{HAND_TOTAL[convo]})")
        print("  per page:", [p["bubbles"] for p in per_page])

    with io.open(OUT, "w", encoding="utf-8") as handle:
        # Names, addresses and numbers from the screenshots never reach disk.
        json.dump(redact_tree(report), handle, indent=2, ensure_ascii=False)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
