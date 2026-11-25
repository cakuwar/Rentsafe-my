"""E5: timing (Test A) and 10 concurrent users (Test B) against the separate
rentsafe_exp copy of the stack started by RUN_E5.ps1. Never talks to the demo
ports (4000 / 8000); refuses to run against anything but 4100 / 8100.

    python -I -B e5_run.py --phase A --private DIR --public DIR [--smoke] [--pids NLP_PID,BACKEND_PID]
    python -I -B e5_run.py --phase B --private DIR --public DIR [--smoke] [--pids ...]

Test A: the 15 blind cases once each, cold cache, one at a time. Per case: the
OCR and classifier stages timed directly on the model service, then the full
request through the backend (screenshots + the same form fields as the blind
test). Scores and bands are compared with Table 4.11.
Test B: B1 10 users x 3 minutes on the text endpoint, each user its own client
address; B2 the same from one shared address, to show the rate limit; B3 10
simultaneous screenshot requests, one each. No agent identifiers anywhere.

Chat text and full API responses go to --private (outside the repo); --public
gets timings, statuses and scores only.
"""
import argparse
import csv
import json
import os
import random
import statistics
import sys
import threading
import time
from urllib.parse import urlparse

import psutil
import requests

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CASES = os.path.join(REPO, "data", "test_real", "cases")
TRANSCRIPTS = os.path.join(os.path.expanduser("~"), "rentsafe_experiments_data", "blind", "blind_transcripts.csv")
BACKEND = "http://127.0.0.1:4100/api"
NLP = "http://127.0.0.1:8100"
# Table 4.11, in case order 1..15 (the user's E5 brief).
TABLE_411 = [59, 59, 11, 0, 49, 53, 58, 59, 57, 64, 26, 74, 64, 64, 0]

for url in (BACKEND, NLP):
    if urlparse(url).port not in (4100, 8100):
        raise SystemExit(f"refusing to run against {url}: only the rentsafe_exp ports 4100 / 8100 are allowed")


# --------------------------------------------------------------------- helpers
class Sampler(threading.Thread):
    """Free memory, CPU and the RSS of the two services, once a second."""

    def __init__(self, pids):
        super().__init__(daemon=True)
        self.pids, self.rows, self.stop_flag = pids, [], threading.Event()
        psutil.cpu_percent(None)

    def rss(self, pid):
        try:
            p = psutil.Process(pid)
            return sum(x.memory_info().rss for x in [p] + p.children(recursive=True)) / 2**20
        except psutil.Error:
            return None

    def run(self):
        while not self.stop_flag.wait(1.0):
            vm = psutil.virtual_memory()
            self.rows.append({"t": time.time(), "available_mb": vm.available / 2**20, "cpu_pct": psutil.cpu_percent(None),
                              **{f"rss_{k}_mb": self.rss(v) for k, v in self.pids.items()}})

    def summary(self):
        self.stop_flag.set()
        if not self.rows:
            return {}
        out = {"samples": len(self.rows),
               "available_mb_min": round(min(r["available_mb"] for r in self.rows)),
               "available_mb_median": round(statistics.median(r["available_mb"] for r in self.rows)),
               "cpu_pct_mean": round(statistics.mean(r["cpu_pct"] for r in self.rows), 1)}
        for k in self.pids:
            vals = [r[f"rss_{k}_mb"] for r in self.rows if r[f"rss_{k}_mb"] is not None]
            if vals:
                out[f"rss_{k}_mb_max"] = round(max(vals))
        return out


def pct(values, q):
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return round(s[f] + (s[c] - s[f]) * (k - f), 3)


def latency_stats(records):
    ok = [r["latency_s"] for r in records if r["status"] == 200]
    n = len(records)
    errors = [r for r in records if r["status"] not in (200, 429)]
    return {"requests": n, "ok": len(ok), "http_429": sum(r["status"] == 429 for r in records),
            "errors": len(errors), "error_rate": round(len(errors) / n, 4) if n else None,
            "error_kinds": sorted({str(r["status"]) + (":" + r["error"][:60] if r.get("error") else "") for r in errors}),
            "p50_s": pct(ok, 0.50), "p95_s": pct(ok, 0.95), "max_s": round(max(ok), 3) if ok else None,
            "mean_s": round(statistics.mean(ok), 3) if ok else None,
            "explanation_present": sum(bool(r.get("narrative")) for r in records if r["status"] == 200)}


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def case_files(case_id):
    case_dir = os.path.join(CASES, case_id)
    case = json.load(open(os.path.join(case_dir, "input.json"), encoding="utf-8-sig"))
    files = [("files", (page, open(os.path.join(case_dir, page), "rb").read(),
                        "image/png" if page.lower().endswith(".png") else "image/jpeg")) for page in case["pages"]]
    return case, files


def form_fields(case):
    agent, prop = case.get("agent", {}), case.get("property", {})
    fields = {"agentName": agent.get("name", ""), "agentPhone": agent.get("phone", ""), "renNumber": agent.get("ren", ""),
              "company": agent.get("company", ""), "price": prop.get("price", ""), "area": prop.get("area", ""),
              "propertyType": prop.get("propertyType", ""), "bedrooms": prop.get("bedrooms", ""),
              "roomType": prop.get("roomType", ""), "language": case.get("language", "auto")}
    return {k: v for k, v in fields.items() if v != ""}


def points(result, name):
    return ((result.get("components") or {}).get(name) or {}).get("points")


# ---------------------------------------------------------------------- Test A
def test_a(args, sampler):
    expected = {r["case_id"]: r for r in csv.DictReader(open(os.path.join(CASES, "results.csv"), encoding="utf-8-sig"))}
    ids = ["case01", "case04"] if args.smoke else [f"case{i:02d}" for i in range(1, 16)]
    rows, raw = [], []
    # One untimed warm-up on the model service only (the smoke run showed the first
    # OCR call after start-up is slower: 6.5 s against 4.8 s for the same pages a
    # moment later). The backend, Redis and the paid services stay cold.
    case, files = case_files("case04")
    t = time.perf_counter()
    warm = requests.post(f"{NLP}/ocr", files=files, timeout=300)
    requests.post(f"{NLP}/classify", json={"text": warm.json()["extracted_text"], "language": "auto"}, timeout=300)
    warmup_s = round(time.perf_counter() - t, 3)
    for cid in ids:
        case, files = case_files(cid)
        t = time.perf_counter()
        ocr = requests.post(f"{NLP}/ocr", files=files, timeout=300)
        t_ocr = time.perf_counter() - t
        ocr.raise_for_status()
        text = ocr.json()["extracted_text"]
        t = time.perf_counter()
        cls = requests.post(f"{NLP}/classify", json={"text": text, "language": case.get("language", "auto")}, timeout=300)
        t_cls = time.perf_counter() - t
        cls.raise_for_status()
        t = time.perf_counter()
        resp = requests.post(f"{BACKEND}/analyze/screenshot", files=files, data=form_fields(case), timeout=300)
        t_e2e = time.perf_counter() - t
        result = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        exp = expected.get(cid, {})
        osint = ((result.get("evidence") or {}).get("osint") or {})
        idx = int(cid[-2:]) - 1
        row = {
            "case_id": cid, "http_status": resp.status_code, "pages": len(files),
            "ocr_s": round(t_ocr, 3), "classify_s": round(t_cls, 3), "end_to_end_s": round(t_e2e, 3),
            "rest_s": round(t_e2e - t_ocr - t_cls, 3),
            "score": result.get("riskScore"), "max": result.get("maxPossibleScore"), "band": result.get("riskBand"),
            "table_4_11_score": TABLE_411[idx], "blind_band": exp.get("api_band"),
            "score_matches": result.get("riskScore") == TABLE_411[idx], "band_matches": result.get("riskBand") == exp.get("api_band"),
            "model_prob": round(result["modelProbability"], 4) if isinstance(result.get("modelProbability"), (int, float)) else None,
            "nlp_pts": points(result, "nlp"), "blind_nlp_pts": exp.get("nlp_pts"),
            "osint_pts": points(result, "osint"), "blind_osint_pts": exp.get("osint_pts"),
            "price_pts": points(result, "price"), "blind_price_pts": exp.get("price_pts"),
            "osint_status": osint.get("status"), "osint_verifier": osint.get("verifier"),
            "explanation": bool((result.get("narrative") or {}).get("en")),
            "explanation_provider": (result.get("narrative") or {}).get("provider"),
            "ocr_messages_direct": ocr.json().get("turns"), "ocr_messages_backend": (result.get("ocr") or {}).get("messages"),
        }
        rows.append(row)
        raw.append({"case_id": cid, "result": result})
        print(f"  {cid}: HTTP {resp.status_code}  {row['score']}/{row['max']} {row['band']} (Table 4.11: {TABLE_411[idx]})  "
              f"ocr {t_ocr:.1f}s  classify {t_cls:.1f}s  end-to-end {t_e2e:.1f}s", flush=True)
    with open(os.path.join(args.private, "test_a_raw.jsonl"), "w", encoding="utf-8") as f:
        for r in raw:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    write_csv(os.path.join(args.public, "test_a.csv"), rows)
    e2e = [r["end_to_end_s"] for r in rows if r["http_status"] == 200]
    summary = {
        "cases": len(rows), "http_200": sum(r["http_status"] == 200 for r in rows),
        "score_matches_table_4_11": sum(r["score_matches"] for r in rows), "band_matches": sum(r["band_matches"] for r in rows),
        "mismatches": [{k: r[k] for k in ("case_id", "score", "table_4_11_score", "band", "blind_band", "nlp_pts", "blind_nlp_pts",
                                            "osint_pts", "blind_osint_pts", "price_pts", "blind_price_pts", "osint_status")}
                       for r in rows if not (r["score_matches"] and r["band_matches"])],
        "end_to_end_total_s": round(sum(e2e), 2), "end_to_end_median_s": pct(e2e, 0.5), "end_to_end_max_s": max(e2e) if e2e else None,
        "ocr_median_s": pct([r["ocr_s"] for r in rows], 0.5), "classify_median_s": pct([r["classify_s"] for r in rows], 0.5),
        "rest_median_s": pct([r["rest_s"] for r in rows], 0.5),
        "explanations": sum(r["explanation"] for r in rows),
        "model_service_warmup_s": warmup_s,
        "resources": sampler.summary(),
    }
    return summary


# ---------------------------------------------------------------------- Test B
def load_transcripts():
    return [r for r in csv.DictReader(open(TRANSCRIPTS, encoding="utf-8"))]


def post_text(session, text, xff):
    t = time.perf_counter()
    try:
        r = session.post(f"{BACKEND}/analyze", json={"text": text, "language": "auto"},
                         headers={"X-Forwarded-For": xff}, timeout=120)
        lat = time.perf_counter() - t
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        return lat, r.status_code, body, None
    except requests.RequestException as e:
        return time.perf_counter() - t, -1, {}, type(e).__name__


def load_run(label, transcripts, users, duration, cap, shared_xff=None, stop_after_429_s=None):
    """`users` threads post transcripts back to back until `duration` or `cap` requests."""
    records, lock, sent = [], threading.Lock(), [0]
    first_429 = [None]
    t0 = time.perf_counter()

    def worker(i):
        session, k = requests.Session(), 0
        xff = shared_xff or f"10.6.{label_octet[label]}.{i + 1}"
        while True:
            now = time.perf_counter() - t0
            if now >= duration:
                break
            if stop_after_429_s is not None and first_429[0] is not None and now - first_429[0] >= stop_after_429_s:
                break
            with lock:
                if sent[0] >= cap:
                    break
                sent[0] += 1
                seq = sent[0]
            row = transcripts[(i + k) % len(transcripts)]
            k += 1
            start = time.perf_counter() - t0
            lat, status, body, err = post_text(session, row["text"], xff)
            if status == 429 and first_429[0] is None:
                first_429[0] = time.perf_counter() - t0
            with lock:
                records.append({"test": label, "user": i + 1, "seq": seq, "case_id": row["case_id"], "start_s": round(start, 3),
                                "latency_s": round(lat, 3), "status": status, "band": body.get("riskBand"),
                                "score": body.get("riskScore"), "nlp_status": body.get("nlpStatus"),
                                "narrative": bool((body.get("narrative") or {}).get("en")), "error": err or (body.get("error") if status != 200 else None)})

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(users)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    wall = time.perf_counter() - t0
    records.sort(key=lambda r: r["seq"])
    stats = latency_stats(records)
    stats.update({"users": users, "wall_s": round(wall, 1), "throughput_per_min": round(stats["ok"] / wall * 60, 1) if wall else None,
                  "first_429_at_s": round(first_429[0], 1) if first_429[0] is not None else None,
                  "ok_before_first_429": sum(1 for r in records if r["status"] == 200 and (first_429[0] is None or r["start_s"] < first_429[0]))})
    return records, stats


label_octet = {"B1": 1, "B2": 2}


def screenshot_burst(ids):
    barrier = threading.Barrier(len(ids))
    out = []
    lock = threading.Lock()

    def one(i, cid):
        case, files = case_files(cid)
        barrier.wait()
        t = time.perf_counter()
        try:
            r = requests.post(f"{BACKEND}/analyze/screenshot", files=files, data={"language": case.get("language", "auto")},
                              headers={"X-Forwarded-For": f"10.6.3.{i + 1}"}, timeout=300)
            lat, status = time.perf_counter() - t, r.status_code
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            err = None
        except requests.RequestException as e:
            lat, status, body, err = time.perf_counter() - t, -1, {}, type(e).__name__
        with lock:
            out.append({"test": "B3", "user": i + 1, "seq": i + 1, "case_id": cid, "start_s": 0.0, "latency_s": round(lat, 3),
                        "status": status, "band": body.get("riskBand"), "score": body.get("riskScore"),
                        "nlp_status": body.get("nlpStatus"), "narrative": bool((body.get("narrative") or {}).get("en")),
                        "error": err or (body.get("error") if status != 200 else None)})

    threads = [threading.Thread(target=one, args=(i, cid)) for i, cid in enumerate(ids)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    out.sort(key=lambda r: r["user"])
    return out, latency_stats(out)


def test_b(args, pids):
    transcripts = load_transcripts()
    assert len(transcripts) == 15, len(transcripts)
    random.Random(42).shuffle(transcripts)  # fixed order, so the run can be repeated
    summary, all_records = {}, []

    s = Sampler(pids); s.start()
    print("  B1: 10 users, separate client addresses", flush=True)
    rec, st = load_run("B1", transcripts, users=10, duration=20 if args.smoke else 180, cap=30 if args.smoke else 600)
    st["resources"] = s.summary(); summary["B1_separate_clients"] = st; all_records += rec
    print(f"     {st}", flush=True)

    if not args.smoke:
        time.sleep(10)
        s = Sampler(pids); s.start()
        print("  B2: 10 users, one shared client address (rate limit 100 per 15 minutes)", flush=True)
        rec, st = load_run("B2", transcripts, users=10, duration=180, cap=150, shared_xff="10.6.2.1", stop_after_429_s=20)
        st["resources"] = s.summary(); summary["B2_shared_address"] = st; all_records += rec
        print(f"     {st}", flush=True)

    time.sleep(10)
    s = Sampler(pids); s.start()
    ids = ["case01", "case04"] if args.smoke else [f"case{i:02d}" for i in range(1, 11)]
    print(f"  B3: {len(ids)} simultaneous screenshot requests", flush=True)
    rec, st = screenshot_burst(ids)
    st["resources"] = s.summary(); summary["B3_screenshot_burst"] = st; all_records += rec
    print(f"     {st}", flush=True)

    write_csv(os.path.join(args.public, "test_b_requests.csv"), all_records)
    return summary


# ------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["A", "B"], required=True)
    ap.add_argument("--private", required=True)
    ap.add_argument("--public", required=True)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--pids", default="")
    ap.add_argument("--label", default="")
    args = ap.parse_args()
    for d in (args.private, args.public):
        os.makedirs(d, exist_ok=True)
    if os.path.commonpath([os.path.abspath(args.private), REPO]) == REPO:
        raise SystemExit("--private must be outside the repo")
    pids = {}
    if args.pids:
        nlp_pid, backend_pid = (int(x) for x in args.pids.split(","))
        pids = {"nlp": nlp_pid, "backend": backend_pid}

    requests.get(f"{NLP}/health", timeout=10).raise_for_status()
    requests.get(f"{BACKEND}/health", timeout=10).raise_for_status()
    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if args.phase == "A":
        sampler = Sampler(pids); sampler.start()
        summary = test_a(args, sampler)
    else:
        summary = test_b(args, pids)
    summary = {"phase": args.phase, "label": args.label, "smoke": args.smoke, "started": started,
               "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "cpu_logical": psutil.cpu_count(),
               "ram_total_gb": round(psutil.virtual_memory().total / 2**30, 1), **summary}
    path = os.path.join(args.public, f"summary_{args.phase}.json")
    json.dump(summary, open(path, "w", encoding="utf-8"), indent=1)
    print(f"  summary -> {path}")


if __name__ == "__main__":
    main()
