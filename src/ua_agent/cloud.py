# -*- coding: utf-8 -*-
"""GitHub 云端标注链路（REST API，无需 gh CLI）：
关键帧/原片上传 Release → clips.csv 追加（预览链接靠前、人工回填列靠前）→ 人工确认真值。

环境：GITHUB_TOKEN、UA_CLOUD_REPO；可选 UA_PAGES_BASE（Pages 播放页前缀，用于拼 preview_url）
"""
from __future__ import annotations

import csv
import json
import mimetypes
import os
from pathlib import Path

import requests

API = "https://api.github.com"
UPLOAD = "https://uploads.github.com"

# clips.csv 列顺序：预览/人工回填前置，方便审核
COLUMNS = ["clip_id", "game", "format", "preview_url", "human_correction", "review_status",
           "pr_p", "pr_conf", "content_label", "content_vae", "comment_pred",
           "source_url", "video_download_url", "keyframe_url", "duration_sec", "resolution",
           "notes", "file"]


class CloudPublisher:
    def __init__(self, repo: str | None = None, token: str | None = None,
                 tag: str = "clips", csv_path: str | Path = "data/clips.csv",
                 upload: str = "keyframes", pages_base: str | None = None):
        self.repo = repo or os.environ.get("UA_CLOUD_REPO", "")
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.tag = tag
        self.csv_path = Path(csv_path)
        self.upload = upload
        self.pages_base = (pages_base or os.environ.get("UA_PAGES_BASE", "")).rstrip("/")
        self._release_id = None
        self._dry = not (self.repo and self.token)

    def _h(self):
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"}

    def _ensure_release(self) -> int:
        if self._release_id:
            return self._release_id
        r = requests.get(f"{API}/repos/{self.repo}/releases/tags/{self.tag}", headers=self._h(), timeout=30)
        if r.status_code == 200:
            self._release_id = r.json()["id"]
            return self._release_id
        r = requests.post(f"{API}/repos/{self.repo}/releases", headers=self._h(),
                          json={"tag_name": self.tag, "name": self.tag,
                                "body": "素材标注批次（AI 预标 + 待人工确认）"}, timeout=60)
        r.raise_for_status()
        self._release_id = r.json()["id"]
        return self._release_id

    def upload_asset(self, path: str | Path, name: str | None = None) -> str:
        if self._dry or self.upload == "none":
            return ""
        p = Path(path)
        if p.stat().st_size > 2 * 1024**3:
            raise ValueError(f"{p.name} 超过 GitHub 单文件 2GB 限制")
        rid = self._ensure_release()
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        url = f"{UPLOAD}/repos/{self.repo}/releases/{rid}/assets?name={name or p.name}"
        with open(p, "rb") as f:
            r = requests.post(url, headers={**self._h(), "Content-Type": ctype}, data=f, timeout=600)
        r.raise_for_status()
        return r.json().get("browser_download_url", "")

    # ---------- clips.csv ----------
    def register(self, annotation: dict, video_path: str, preview_rel: str = "",
                 video_url: str = "", keyframe_url: str = "") -> dict:
        s = annotation.get("sentiment") or {}
        c = s.get("content") or {}
        pm = (s.get("pr_mapping") or {})
        cm = s.get("comments") or {}
        row = {
            "clip_id": annotation.get("clip_id", ""),
            "game": annotation.get("game", ""),
            "format": annotation.get("format", ""),
            "preview_url": (self.pages_base + "/" + preview_rel.lstrip("/")) if (self.pages_base and preview_rel) else "",
            "human_correction": "",
            "review_status": "pending",
            "pr_p": "、".join(p["id"] for p in (annotation.get("pr") or {}).get("p_codes") or []),
            "pr_conf": (annotation.get("pr") or {}).get("confidence", ""),
            "content_label": c.get("label", ""),
            "content_vae": f"v={c.get('valence')};a={c.get('arousal')};d={c.get('dominance')}",
            "comment_pred": json.dumps({"label": pm.get("label"), "dist": pm.get("dist"),
                                        "obs": {"net": cm.get("net"), "dist": cm.get("dist")}},
                                       ensure_ascii=False) if pm else "",
            "source_url": annotation.get("source", ""),
            "video_download_url": video_url,
            "keyframe_url": keyframe_url,
            "duration_sec": annotation.get("meta", {}).get("duration_sec", ""),
            "resolution": f"{annotation.get('meta', {}).get('width')}x{annotation.get('meta', {}).get('height')}",
            "notes": "",
            "file": Path(video_path).name,
        }
        self._append_csv(row)
        return row

    def _append_csv(self, row: dict):
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        if self.csv_path.exists():
            with open(self.csv_path, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
        rows = [r for r in rows if r.get("clip_id") != row["clip_id"]] + [row]
        with open(self.csv_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(rows)

    def publish(self, annotation: dict, video_path: str, keyframes: list[str] | None = None,
                preview_rel: str = "") -> dict:
        keyframe_url = video_url = ""
        if self.upload in ("both", "keyframes") and keyframes:
            try:
                keyframe_url = self.upload_asset(keyframes[0])
            except Exception as e:
                print(f"[cloud] 关键帧上传失败：{e}")
        if self.upload == "both":
            try:
                video_url = self.upload_asset(video_path)
            except Exception as e:
                print(f"[cloud] 视频上传失败：{e}")
        self.register(annotation, video_path, preview_rel, video_url, keyframe_url)
        return {"video_url": video_url, "keyframe_url": keyframe_url,
                "csv": str(self.csv_path), "dry_run": self._dry}


if __name__ == "__main__":
    print("CloudPublisher ready（dry-run = 无 GITHUB_TOKEN / UA_CLOUD_REPO）")
