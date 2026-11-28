# -*- coding: utf-8 -*-
"""Run Task-A extraction over a folder of item JSONs -> rows.csv + logs.jsonl.

Usage:
    DEEPSEEK_API_KEY=... python src/run.py data/samples -o out/            # live
    python src/run.py data/samples -o out/ --mock                          # offline demo

Guardrails:
  * writes are restricted to the --out directory (and that directory must stay under CWD),
  * per-attempt network timeout (--timeout, default 120s) so a stalled response cannot wedge the
    run: a healthy item is one call, a pathological one is at most REPAIRS+1 calls,
  * bounded workers (max 8), failures are logged and skipped -- never abort the whole run.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract import ItemError, extract  # noqa: E402

MAX_WORKERS = 8
COLS = ["clip_id", "status", "stance", "intensity", "stance_evidence", "p_codes", "r_codes",
        "confidence", "one_liner", "attempts", "ms"]


def load_items(folder: Path) -> list[dict]:
    items = []
    for f in sorted(folder.rglob("*.json")):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(j, dict) and ("video_id" in j or "frames" in j or "title" in j):
            j.setdefault("video_id", f.stem)
            items.append(j)
    return items


def check_out_dir(out: Path) -> None:
    out_abs = out.resolve()
    cwd = Path.cwd().resolve()
    if cwd not in out_abs.parents and out_abs != cwd:
        raise SystemExit(f"refusing to write outside the working directory: {out_abs}")


def one(item: dict, mock: bool, timeout_s: int) -> dict:
    log: list = []
    t0 = time.time()
    try:
        rec = extract(item, mock=mock, log=log, timeout_s=timeout_s)
        cs = rec["content_sentiment"]
        row = {"clip_id": item.get("video_id"), "status": "ok", "stance": cs["label"],
               "intensity": cs["intensity"], "stance_evidence": cs["evidence"],
               "p_codes": ";".join(x["id"] for x in rec["p_codes"]),
               "r_codes": ";".join(rec["r_codes_hit"]), "confidence": rec["confidence"],
               "one_liner": rec["one_liner"], "attempts": len(log),
               "ms": int((time.time() - t0) * 1000)}
    except ItemError as e:
        row = {"clip_id": item.get("video_id"), "status": f"skipped:{e}", "attempts": 0,
               "ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        row = {"clip_id": item.get("video_id"), "status": f"failed:{str(e)[:160]}",
               "attempts": len(log), "ms": int((time.time() - t0) * 1000)}
    return {"row": row, "log": {"clip_id": item.get("video_id"), "attempts": log}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_dir", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=Path("out"))
    ap.add_argument("--mock", action="store_true", help="offline deterministic demo (no API calls)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    check_out_dir(args.out)
    args.out.mkdir(parents=True, exist_ok=True)
    items = load_items(args.input_dir)
    if args.limit:
        items = items[:args.limit]
    if not items:
        raise SystemExit(f"no item JSON found under {args.input_dir}")
    workers = max(1, min(args.workers, MAX_WORKERS))
    print(f"items={len(items)} workers={workers} mock={args.mock} -> {args.out}")

    rows, logs = [], []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(one, it, args.mock, args.timeout): it for it in items}
        for done_n, f in enumerate(as_completed(futs), 1):
            res = f.result()
            rows.append(res["row"])
            logs.append(res["log"])
            r = res["row"]
            print(f"  [{done_n}/{len(futs)}] {r.get('clip_id')} {r.get('status')} "
                  f"{r.get('stance', '')} {r.get('ms', '')}ms", flush=True)

    rows.sort(key=lambda r: str(r.get("clip_id")))
    with open(args.out / "rows.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    with open(args.out / "logs.jsonl", "w", encoding="utf-8") as fh:
        for lg in logs:
            fh.write(json.dumps(lg, ensure_ascii=False) + "\n")
    ok = sum(1 for r in rows if r["status"] == "ok")
    skipped = sum(1 for r in rows if str(r["status"]).startswith("skipped"))
    failed = sum(1 for r in rows if r["status"] not in ("ok",) and not str(r["status"]).startswith("skipped"))
    print(f"ok={ok} skipped={skipped} failed={failed} total={len(rows)} in {time.time() - t0:.1f}s")
    print(f"rows -> {args.out / 'rows.csv'} ; logs -> {args.out / 'logs.jsonl'}")


if __name__ == "__main__":
    main()
