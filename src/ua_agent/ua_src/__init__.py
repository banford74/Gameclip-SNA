"""项目入口包。

子目标拆分：
  G1 抽帧         src/extractor/frame_extractor.py
  G2 关键帧筛选    src/extractor/keyframe_selector.py
  G3 画面识别      src/vision/frame_analyzer.py (+ vlm_client.py)
  G4 评论采集      src/platforms/* + src/comments/comment_collector.py
  G5 评论情感      src/comments/sentiment_analyzer.py
  G6 聚合与报告    src/report/*
顶层编排见 src/pipeline.py
"""

__version__ = "0.1.0"
