"""Sanity table for the two embedding candidates, before any real evaluation.

Pairs chosen by the author: some should match across Malay, English and slang,
some should NOT (negation; a renter's question vs an owner's demand). Plus the
CPU time to embed every message of a real chat. The model is chosen later on
the minimal-pair results, not on this table.

    python eval/semantic_sanity.py

Writes eval/results/semantic_flags/sanity.json and sanity.md.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
NLP = os.path.dirname(HERE)
sys.path.insert(0, NLP)
sys.path.insert(0, HERE)

from embedders import E5, MESOLITICA, Embedder  # noqa: E402

OUT = os.path.join(HERE, "results", "semantic_flags")
PAIRS = [
    ("should match", "byr dlu baru blh tgk", "pay first before viewing"),
    ("should match", "rumah berkunci, tak boleh masuk tengok", "the unit is locked, no viewing"),
    ("should match", "I hantar keys by Poslaju", "kunci saya pos"),
    ("should NOT match", "jangan bayar sebelum tengok", "bayar dulu sebelum tengok"),
    ("should NOT match", "boleh viewing dulu?", "bayar dulu baru viewing"),
]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(OUT, exist_ok=True)
    gates = json.load(open(os.path.join(NLP, "training", "gates.json"), encoding="utf-8"))
    chats = {name: [l.split(": ", 1)[-1] for l in gates[name]["text"].split("\n") if l.strip()]
             for name in ("real_scam_production", "real_legit_production")}

    report = {"pairs": [], "timing": {}}
    rows = {}
    for name in (E5, MESOLITICA):
        start = time.perf_counter()
        embedder = Embedder(name)
        load = time.perf_counter() - start
        sims = []
        for kind, a, b in PAIRS:
            va, vb = embedder.encode([a, b])
            sims.append(float(va @ vb))
        rows[name] = sims
        timing = {"load_seconds": round(load, 1),
                  "params_millions": round(sum(p.numel() for p in embedder.model.parameters()) / 1e6)}
        for chat, messages in chats.items():
            embedder.cache.clear()
            start = time.perf_counter()
            embedder.encode(messages)
            timing[f"{chat}_seconds"] = round(time.perf_counter() - start, 3)
            timing[f"{chat}_messages"] = len(messages)
        report["timing"][name] = timing

    lines = [f"| pair | expected | e5-base | mesolitica 64M |", "|---|---|---|---|"]
    for i, (kind, a, b) in enumerate(PAIRS):
        e5, meso = rows[E5][i], rows[MESOLITICA][i]
        report["pairs"].append({"a": a, "b": b, "expected": kind,
                                "e5": round(e5, 4), "mesolitica": round(meso, 4)})
        lines.append(f"| \"{a}\" vs \"{b}\" | {kind} | {e5:.3f} | {meso:.3f} |")
    for label in ("params_millions", "load_seconds", "real_scam_production_seconds",
                  "real_legit_production_seconds"):
        lines.append(f"| {label} | | {report['timing'][E5][label]} | {report['timing'][MESOLITICA][label]} |")
    table = "\n".join(lines)
    json.dump(report, open(os.path.join(OUT, "sanity.json"), "w", encoding="utf-8"), indent=2,
              ensure_ascii=False)
    open(os.path.join(OUT, "sanity.md"), "w", encoding="utf-8").write(table + "\n")
    print(table)


if __name__ == "__main__":
    main()
