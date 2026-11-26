#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证 Apps Script 同步端点是否可用。

用法:
    python scripts/test_sync_endpoint.py https://script.google.com/macros/s/xxx/exec

行为:
  1) GET 端点 → 打印状态/返回（应看到 ok + spreadsheetUrl）
  2) POST 一条测试标注（annotator=test, clip_id=__probe__）→ 打印结果
  3) 再 GET 一次（可选看 rows 增长）
测试数据会留在 Sheet 里，可手动删除 annotator=test 的那行。
"""
import json
import sys

import requests

URL = sys.argv[1] if len(sys.argv) > 1 else ""
if not URL:
    sys.exit(__doc__)


def main():
    print("GET", URL)
    try:
        r = requests.get(URL, timeout=30)
        print("  status", r.status_code)
        print("  body:", r.text[:300])
    except Exception as e:
        print("  GET FAIL:", type(e).__name__, str(e)[:160])

    payload = {
        "annotator": "test",
        "saved_at": "2026-01-01T00:00:00Z",
        "count": 1,
        "labels": {
            "__probe__": {
                "stance": "neutral", "intensity": 1, "p_codes": "", "r_codes": "",
                "evidence": "probe", "confidence": 0.5, "notes": "endpoint self-test",
                "annotated_at": "2026-01-01T00:00:00Z",
            }
        },
    }
    print("POST", URL)
    try:
        r = requests.post(URL, data=json.dumps(payload), headers={"Content-Type": "text/plain"}, timeout=60)
        print("  status", r.status_code)
        print("  body:", r.text[:300])
        try:
            j = r.json()
            if j.get("spreadsheetUrl"):
                print("  sheet:", j["spreadsheetUrl"])
        except Exception:
            pass
    except Exception as e:
        print("  POST FAIL:", type(e).__name__, str(e)[:160])


if __name__ == "__main__":
    main()
