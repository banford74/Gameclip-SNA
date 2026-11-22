"""图像工具：感知哈希（去重）、模糊度检测（清晰度）。

纯 PIL/numpy/cv2 实现，无额外依赖。
"""
from __future__ import annotations

import hashlib
import os
from typing import Union

import cv2
import numpy as np
from PIL import Image

PathLike = Union[str, "os.PathLike"]


def load_cv(path: PathLike) -> np.ndarray:
    """用 cv2 读取图像为 BGR numpy 数组。"""
    img = cv2.imread(str(path))
    if img is None:
        raise FileNotFoundError(f"无法读取图像: {path}")
    return img


def blur_score(path: PathLike) -> float:
    """拉普拉斯方差：值越大越清晰，越小越模糊。"""
    gray = cv2.cvtColor(load_cv(path), cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def dhash(path: PathLike, hash_size: int = 8) -> str:
    """差分感知哈希（dhash），返回 16 进制字符串。

    对尺寸/压缩不敏感，适合视频相邻帧去重。
    """
    img = Image.open(str(path)).convert("L")
    img = img.resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
    pixels = np.asarray(img, dtype=np.int16)
    diff = pixels[:, 1:] > pixels[:, :-1]
    bits = diff.flatten()
    # 打包成整数 -> 十六进制
    value = 0
    for b in bits:
        value = (value << 1) | int(b)
    return f"{value:0{((hash_size * hash_size + 3) // 4)}x}"


def hamming(a: str, b: str) -> int:
    """两个十六进制哈希的汉明距离。"""
    if len(a) != len(b):
        # 长度不一致时用字符串逐字符比较
        return sum(c1 != c2 for c1, c2 in zip(a, b)) + abs(len(a) - len(b))
    ia, ib = int(a, 16), int(b, 16)
    return bin(ia ^ ib).count("1")


def histogram_distance(a: PathLike, b: PathLike) -> float:
    """相邻帧直方图相关系数（1=完全一致，0=完全不同）。返回 1 - corr。"""
    ha = cv2.calcHist([load_cv(a)], [0, 1, 2], None, [8, 8], [0, 256, 0, 256])
    hb = cv2.calcHist([load_cv(b)], [0, 1, 2], None, [8, 8], [0, 256, 0, 256])
    cv2.normalize(ha, ha)
    cv2.normalize(hb, hb)
    corr = cv2.compareHist(ha, hb, cv2.HISTCMP_CORREL)
    return float(1.0 - corr)


def file_md5(path: PathLike) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
