"""E4. GPT-4o-mini zero-shot baseline.

    python scripts/e4_gpt.py --dry-run     # no network: what would be sent, call count, cost estimate
    python scripts/e4_gpt.py --run         # the API calls (needs OPENAI_API_KEY in the environment)

The prompt and every model setting come from prompts/e4_prompt.json, frozen
before any call; the script refuses to run if its SHA-256 differs from
prompts/e4_prompt.sha256. Every text is anonymised (scripts/anonymise.py)
before it leaves the machine; the exact texts sent are written to
results/e4/sent_inputs.jsonl. The API key is read from the environment only
and is never printed or logged.
"""
import argparse
import csv
import hashlib
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anonymise import anonymise, leaks  # noqa: E402
from common import BLIND_FILE, LABELS, PRIVATE, RESULTS, ROOT, load, metrics, pair_accuracy, wilson  # noqa: E402

PROMPT = os.path.join(ROOT, "prompts", "e4_prompt.json")
PROMPT_HASH = os.path.join(ROOT, "prompts", "e4_prompt.sha256")
OUT = os.path.join(RESULTS, "e4")                 # metrics and estimates only
PRIVATE_OUT = os.path.join(PRIVATE, "e4")         # texts sent and raw API replies (chat text)
CASES_CSV = r"C:\Users\U S E R\Documents\fyp\rentsafe-my\data\test_real\cases\results.csv"
URL = "https://api.openai.com/v1/chat/completions"


def items():
    out = []
    val = load("val.csv")
    for i, r in val.iterrows():
        out.append({"id": f"val_{i:03d}", "set": "validation_95", "label": r.label, "origin": r.origin,
                    "text": r.text})
    fig = load("fig43_pairs_test.csv")
    fig = fig[fig["kind"] == "full"]
    for _, r in fig.iterrows():
        out.append({"id": f"pair_{r.pair_id}_{r.label[:5]}", "set": "new_wording_144", "label": r.label,
                    "pair_id": r.pair_id, "lang": r.lang, "origin": "synthetic", "text": r.text})
    if os.path.exists(BLIND_FILE):
        import pandas as pd
        blind = pd.read_csv(BLIND_FILE)
        for _, r in blind.iterrows():
            out.append({"id": r.case_id, "set": "blind_15", "label": r.label, "origin": r.origin,
                        "text": r.text})
    for it in out:
        it["text"], it["replacements"] = anonymise(it["text"])
        it["leaks_after"] = leaks(it["text"])
    return out


def estimate(its, cfg):
    sys_tokens = len(cfg["system"]) / 3 + 10
    tokens_in = sum(len(it["text"]) / 3 + sys_tokens for it in its)
    blind_missing = not any(it["set"] == "blind_15" for it in its)
    blind_tokens = 0
    if blind_missing:   # rough size from the recorded OCR message counts: 60 characters a message
        with open(CASES_CSV, encoding="utf-8-sig", newline="") as handle:
            msgs = [int(r["ocr_messages"] or 0) for r in csv.DictReader(handle)]
        blind_tokens = sum(n * 60 / 3 + sys_tokens for n in msgs)
    calls = len(its) + (15 if blind_missing else 0)
    tin = tokens_in + blind_tokens
    tout = calls * cfg["max_tokens"]
    price = cfg["pricing_usd_per_1M_tokens"]
    cost = tin / 1e6 * price["input"] + tout / 1e6 * price["output"]
    return {"calls": calls, "input_tokens_est": round(tin), "output_tokens_max": tout,
            "cost_usd_est": round(cost, 4), "cost_usd_upper_x3": round(cost * 3, 4),
            "blind_estimated_from_ocr_counts": blind_missing}


def call(cfg, key, text):
    body = json.dumps({
        "model": cfg["model"], "temperature": cfg["temperature"], "seed": cfg["seed"],
        "max_tokens": cfg["max_tokens"], "response_format": cfg["response_format"],
        "messages": [{"role": "system", "content": cfg["system"]},
                     {"role": "user", "content": cfg["user_template"].format(conversation=text)}],
    }).encode()
    for attempt in range(4):
        req = urllib.request.Request(URL, data=body, method="POST", headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
            return {"ok": True, "latency_s": round(time.perf_counter() - start, 3), "attempts": attempt + 1,
                    "content": data["choices"][0]["message"]["content"], "usage": data.get("usage", {}),
                    "model_returned": data.get("model"), "system_fingerprint": data.get("system_fingerprint")}
        except urllib.error.HTTPError as err:
            status = err.code
            detail = err.read()[:300].decode("utf-8", "replace")
            if status == 429 or status >= 500:
                time.sleep(2 ** attempt * 2)
                continue
            return {"ok": False, "error": f"HTTP {status}: {detail}", "attempts": attempt + 1}
        except (urllib.error.URLError, TimeoutError) as err:
            time.sleep(2 ** attempt * 2)
            last = str(err)
            continue
    return {"ok": False, "error": "gave up after retries", "attempts": 4}


def decide(content):
    try:
        obj = json.loads(content)
    except (TypeError, ValueError):
        return None, None
    p = obj.get("p_scam")
    if isinstance(p, (int, float)) and 0 <= p <= 1:
        return ("SCAM" if p >= 0.5 else "LEGITIMATE"), float(p)
    label = str(obj.get("label", "")).strip().lower()
    if label in ("scam", "legitimate"):
        return label.upper(), (1.0 if label == "scam" else 0.0)
    return None, None


def report(rows, cfg):
    import numpy as np
    import pandas as pd
    df = pd.DataFrame(rows)
    ok = df[df["p"].notna()]
    out = {"calls": len(df), "errors": int(df["p"].isna().sum()),
           "error_ids": df.loc[df["p"].isna(), "id"].tolist()}
    lat = [r for r in df["latency_s"].dropna()]
    if lat:
        out["latency_s"] = {"p50": round(statistics.median(lat), 3),
                            "p95": round(float(np.percentile(lat, 95)), 3), "max": round(max(lat), 3),
                            "mean": round(statistics.mean(lat), 3)}
    tin = int(df["prompt_tokens"].fillna(0).sum()); tout = int(df["completion_tokens"].fillna(0).sum())
    price = cfg["pricing_usd_per_1M_tokens"]
    out["tokens"] = {"input": tin, "output": tout}
    out["cost_usd"] = round(tin / 1e6 * price["input"] + tout / 1e6 * price["output"], 4)
    for name in ("validation_95", "new_wording_144", "blind_15"):
        s = ok[ok["set"] == name]
        if s.empty:
            continue
        out[name] = metrics(s["label"], s["p"])
        if name == "new_wording_144":
            out[name]["pair_accuracy"], out[name]["pairs"] = pair_accuracy(s.reset_index(drop=True), s["p"].to_numpy())
            out[name]["by_language"] = {}
            for lang, g in s.groupby("lang"):
                g = g.reset_index(drop=True)
                pa, n = pair_accuracy(g, g["p"].to_numpy())
                m = metrics(g["label"], g["p"])
                out[name]["by_language"][lang] = {"pairs": n, "pair_accuracy": pa, "row_accuracy": m["accuracy"],
                                                  "missed_scams": m["fn"], "false_alarms": m["fp"]}
        if name == "blind_15":
            y = s["label"].map(LABELS); hit = s["p"] >= 0.5
            caught, scams = int((hit & (y == 1)).sum()), int((y == 1).sum())
            alarms, legits = int((hit & (y == 0)).sum()), int((y == 0).sum())
            out[name].update({"scams_caught": f"{caught}/{scams}", "recall_wilson95": wilson(caught, scams),
                              "false_alarms": f"{alarms}/{legits}", "false_alarm_wilson95": wilson(alarms, legits),
                              "per_case": dict(zip(s["id"], s["p"]))})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args()
    cfg = json.load(open(PROMPT, encoding="utf-8"))
    digest = hashlib.sha256(open(PROMPT, "rb").read()).hexdigest()
    assert digest == open(PROMPT_HASH).read().split()[0], "prompt file changed after it was frozen"
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(PRIVATE_OUT, exist_ok=True)
    its = items()
    with open(os.path.join(PRIVATE_OUT, "sent_inputs.jsonl"), "w", encoding="utf-8") as handle:
        for it in its:
            handle.write(json.dumps({k: it[k] for k in ("id", "set", "label", "origin", "replacements",
                                                        "leaks_after", "text")}, ensure_ascii=False) + "\n")
    est = estimate(its, cfg)
    leaking = [it["id"] for it in its if it["leaks_after"]]
    summary = {"prompt_sha256": digest, "estimate": est,
               "texts_by_set": {s: sum(it["set"] == s for it in its) for s in sorted({it["set"] for it in its})},
               "texts_with_replacements": sum(bool(it["replacements"]) for it in its),
               "texts_still_matching_a_pattern": leaking}
    with open(os.path.join(OUT, "dry_run_estimate.json"), "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=1)
    print(json.dumps(summary, indent=1))
    if args.dry_run or not args.run:
        return
    assert not leaking, f"anonymisation incomplete for {leaking}"
    assert any(it["set"] == "blind_15" for it in its), "no blind transcripts yet"
    key = os.environ.get("OPENAI_API_KEY")
    assert key, "OPENAI_API_KEY is not set in the environment"
    rows = []
    with open(os.path.join(PRIVATE_OUT, "raw_outputs.jsonl"), "w", encoding="utf-8") as log:
        for n, it in enumerate(its, 1):
            res = call(cfg, key, it["text"])
            label, p = decide(res.get("content")) if res["ok"] else (None, None)
            usage = res.get("usage") or {}
            row = {"id": it["id"], "set": it["set"], "label": it["label"], "pair_id": it.get("pair_id"),
                   "lang": it.get("lang"), "p": p, "pred": label, "latency_s": res.get("latency_s"),
                   "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens")}
            rows.append(row)
            log.write(json.dumps({**{k: v for k, v in res.items()}, **{"id": it["id"]}}, ensure_ascii=False) + "\n")
            if n % 25 == 0:
                print(f"  {n}/{len(its)} calls")
    result = report(rows, cfg)
    with open(os.path.join(OUT, "e4_results.json"), "w", encoding="utf-8") as handle:
        json.dump({"prompt_sha256": digest, **result}, handle, indent=1, default=str)
    print(json.dumps({k: result[k] for k in ("calls", "errors", "cost_usd", "latency_s") if k in result}, indent=1))


if __name__ == "__main__":
    main()
