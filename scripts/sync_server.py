#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""局域网/Tailscale 标注同步服务（零账号方案）。

用途：4 名标注员不依赖 Google/云服务，直接通过本机 IP 访问标注页并自动回传；
进度汇总页自动刷新。

启动：
    python scripts/sync_server.py            # 默认 0.0.0.0:8787
    python scripts/sync_server.py --port 8787 --data D:/ua_data/annotations_sync.json

标注员访问（把 IP 换成你机器的局域网/Tailscale 地址）：
    标注：    http://10.32.92.208:8787/?a=1        （?a=2..4）
    进度：    http://10.32.92.208:8787/progress.html
同步原理：标注页「💾 存档并回传」按钮/自动保存 → POST /sync（JSON，text/plain 也接受）
        服务端按 (annotator, clip_id) 去重合并（annotated_at 取最新）→ 落盘 JSON，
        并对外提供 /labels.csv 供进度页以 ?data=labels.csv 自动刷新（同源，无需 CORS 烦恼）。
"""
import argparse
import csv
import io
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent          # Gameclip-SNA
DOCS = ROOT / "docs"
STORE = Path("D:/ua_data/annotations_sync.json")
LOCK = threading.Lock()
HEAD = ["annotator", "clip_id", "stance", "intensity", "p_codes", "r_codes",
        "evidence", "confidence", "notes", "annotated_at"]


def load_store() -> dict:
    if STORE.exists():
        try:
            return json.loads(STORE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_store(d: dict) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STORE)


def rows_csv(store: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(HEAD)
    for key, rec in sorted(store.items()):
        a, _, cid = key.partition("|")
        w.writerow([a, cid, rec.get("stance", ""), rec.get("intensity", ""), rec.get("p_codes", ""),
                    rec.get("r_codes", ""), rec.get("evidence", ""), rec.get("confidence", ""),
                    rec.get("notes", ""), rec.get("annotated_at", "")])
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    server_version = "GameclipSync/1.0"

    def _send(self, code, body: bytes, ctype="application/json; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {self.address_string()} {fmt % args}", flush=True)

    def do_OPTIONS(self):
        self._send(204, b"")

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path in ("/", "/index.html"):
            return self._static(DOCS / "index.html", "text/html; charset=utf-8")
        if path == "/progress.html":
            return self._static(DOCS / "progress.html", "text/html; charset=utf-8")
        if path == "/labels.csv":
            with LOCK:
                data = rows_csv(load_store())
            return self._send(200, data.encode("utf-8"), "text/csv; charset=utf-8")
        if path == "/sync/health":
            with LOCK:
                n = len(load_store())
            return self._send(200, json.dumps({"ok": True, "records": n}, ensure_ascii=False).encode())
        return self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        path = unquote(urlparse(self.path).path)
        if path != "/sync":
            return self._send(404, b'{"error":"not found"}')
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n).decode("utf-8", "replace")
            body = json.loads(raw)
        except Exception as e:
            return self._send(400, json.dumps({"error": f"bad json: {e}"}, ensure_ascii=False).encode())
        annotator = str(body.get("annotator") or "").strip()
        labels = body.get("labels") or {}
        if not annotator or not isinstance(labels, dict):
            return self._send(400, b'{"error":"missing annotator/labels"}')
        with LOCK:
            store = load_store()
            n_new = n_upd = 0
            for cid, rec in labels.items():
                if not isinstance(rec, dict) or not rec.get("stance"):
                    continue
                key = f"{annotator}|{cid}"
                old = store.get(key)
                if old and old.get("annotated_at") and rec.get("annotated_at") and old["annotated_at"] > rec["annotated_at"]:
                    continue
                rec = dict(rec)
                rec.pop("annotator", None)
                store[key] = rec
                if old:
                    n_upd += 1
                else:
                    n_new += 1
            save_store(store)
            total = len(store)
        out = {"ok": True, "annotator": annotator, "new": n_new, "updated": n_upd, "total": total}
        return self._send(200, json.dumps(out, ensure_ascii=False).encode())

    def _static(self, p: Path, ctype: str):
        try:
            b = p.read_bytes()
        except Exception:
            return self._send(404, b"not found", "text/plain; charset=utf-8")
        return self._send(200, b, ctype)


def main():
    global STORE
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--data", default=str(STORE))
    args = ap.parse_args()
    STORE = Path(args.data)
    print(f"serving {DOCS} on http://{args.host}:{args.port}", flush=True)
    print(f"store: {STORE}", flush=True)
    print("标注员打开:  http://<本机IP>:%d/?a=1 .. ?a=4" % args.port, flush=True)
    print("进度页:      http://<本机IP>:%d/progress.html?data=labels.csv" % args.port, flush=True)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
