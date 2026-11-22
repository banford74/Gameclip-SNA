# -*- coding: utf-8 -*-
"""
GitHub 云端标注链路（替代迁移包里的 gh CLI，用 REST API + requests）。

流程（对应 ua-clipinsight-skeleton/run_pipeline.py 的 O2 模式）：
  1) 每条素材：视频/关键帧上传到 release assets → 得到公开直链
  2) 追加 clips.csv：预览链接 + AI 预打标 + human_correction（人工真值回填）+ 复核状态
  3) 人工确认后：human_correction 回写 → 作为训练真值（soft_labels / train_taskA 的 gold）

用法：
  from pipeline.ua_agent.cloud import CloudPublisher
  cp = CloudPublisher(repo="owner/repo", token=os.environ["GITHUB_TOKEN"])
  cp.publish(annotation, video_path=..., keyframes=[...], upload="keyframes")
  # 无 token/repo → dry-run：只写 clips.csv 与本地链接

环境：
  GITHUB_TOKEN    必需（repo 权限：contents:write）
  UA_CLOUD_REPO   可选（owner/repo），与 --repo 等价
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


class CloudPublisher:
    def __init__(self, repo: str | None = None, token: str | None = None,
                 tag: str = "clips", csv_path: str | Path = "data/clips.csv",
                 upload: str = "keyframes", chunk_release: bool = True):
        self.repo = repo or os.environ.get("UA_CLOUD_REPO", "")
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.tag = tag
        self.csv_path = Path(csv_path)
        self.upload = upload            # keyframes | both | none
        self.chunk_release = chunk_release
        self._release_id = None
        self._dry = not (self.repo and self.token)

    # ---------- GitHub API ----------
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

    def upload_asset(self, path: str | Path) -> str:
        """上传单个文件到 release，返回公开直链（dry-run 时返回空）。"""
        if self._dry or self.upload == "none":
            return ""
        p = Path(path)
        size = p.stat().st_size
        if size > 2 * 1024**3:
            raise ValueError(f"{p.name} 超过 GitHub 单文件 2GB 限制")
        rid = self._ensure_release()
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        url = f"{UPLOAD}/repos/{self.repo}/releases/{rid}/assets?name={p.name}"
        with open(p, "rb") as f:
            r = requests.post(url, headers={**self._h(), "Content-Type": ctype}, data=f, timeout=600)
        r.raise_for_status()
        return r.json().get("browser_download_url", "")

    # ---------- clips.csv ----------
    def register(self, annotation: dict, video_path: str, keyframes: list[str] | None = None,
                 video_url: str = "", keyframe_url: str = "") -> dict:
        """把一条素材登记进 clips.csv（含 AI 标签、人工回填空列、复核状态）。"""
        row = {
            "clip_id": annotation.get("clip_id", ""),
            "file": Path(video_path).name,
            "game": annotation.get("game", ""),
            "format": annotation.get("format", ""),
            "duration_sec": annotation.get("meta", {}).get("duration_sec", ""),
            "resolution": f"{annotation.get('meta', {}).get('width')}x{annotation.get('meta', {}).get('height')}",
            "source_url": annotation.get("source", ""),
            "cloud_video_url": video_url,
            "keyframe_url": keyframe_url,
            "labels_mode": annotation.get("labels_mode", ""),
            "pr_p": "、".join(p["id"] for p in (annotation.get("pr") or {}).get("p_codes") or []),
            "pr_conf": (annotation.get("pr") or {}).get("confidence", ""),
            "ua10": json.dumps(annotation.get("ua10") or {}, ensure_ascii=False),
            "ai_labels": json.dumps({"pr": annotation.get("pr"), "ua10": annotation.get("ua10")},
                                    ensure_ascii=False)[:9000],
            "human_correction": "",       # 人工真值回填（P/R 修正、情感标注）
            "review_status": "pending",   # pending / accepted / corrected / rejected
            "notes": "",
        }
        self._append_csv(row)
        return row

    def _append_csv(self, row: dict):
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        exists = self.csv_path.exists()
        rows = []
        if exists:
            with open(self.csv_path, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
        rows = [r for r in rows if r.get("clip_id") != row["clip_id"]] + [row]
        with open(self.csv_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(row.keys()))
            w.writeheader()
            w.writerows(rows)

    # ---------- 一键发布 ----------
    def publish(self, annotation: dict, video_path: str, keyframes: list[str] | None = None,
                out_dir: str | None = None) -> dict:
        """上传（可选）+ 登记。返回 {video_url, keyframe_url, csv}。"""
        video_url = keyframe_url = ""
        if self.upload in ("both", "keyframes") and keyframes:
            try:
                keyframe_url = self.upload_asset(keyframes[0])
            except Exception as e:  # 网络/权限问题不阻断登记
                print(f"[cloud] 关键帧上传失败：{e}")
        if self.upload == "both":
            try:
                video_url = self.upload_asset(video_path)
            except Exception as e:
                print(f"[cloud] 视频上传失败：{e}")
        self.register(annotation, video_path, keyframes, video_url, keyframe_url)
        return {"video_url": video_url, "keyframe_url": keyframe_url,
                "csv": str(self.csv_path), "dry_run": self._dry}


if __name__ == "__main__":
    print("CloudPublisher ready（dry-run 模式 = 无 GITHUB_TOKEN / UA_CLOUD_REPO）")
