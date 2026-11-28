# CLAUDE.md — GameClip Codebook (Task A)

Project memory for coding agents working in this folder. Read this before editing anything.

## 1. What this is

A **structured-extraction tool** for short game videos: one video in → one validated record out.
The record is the annotation codebook in code: 4-class **content stance**, **P-codes** (plot layer,
multi-select, frame-evidenced), **R-codes** (visual feature hits), **confidence** 0–1.

This folder is the *portfolio slice* of a larger research repo (`Gameclip-SNA`). Only **Task A**
(content stance + P/R codes) is in scope here. **Task B (comment VAD) is out of scope** — do not add
comment fields to the schema.

## 2. Layout

```
portfolio/
├── README.md            # run / design / results
├── CLAUDE.md            # this file
├── WRITEUP.md           # ~2-page design doc
├── INTERVIEW.md         # 15 canonical agent questions, answered for this project
├── demo/DEMO.md         # 5-slide deck + 3-minute script
├── src/
│   ├── schema.json      # JSON Schema for the record (= the codebook in code)
│   ├── codebook.json    # P/R code definitions (20 P, 96 R) with names/meanings
│   ├── extract.py       # prompt + JSON-mode call + validate + repair + logging
│   ├── run.py           # folder -> out/rows.csv (+ out/logs.jsonl); guardrails
│   ├── robustness.py    # 10 adversarial/messy cases, offline mock
│   └── mcp_server.py    # MCP tools over data/clips.csv (list_clips/get_clip/codebook_stats)
├── data/samples/        # 3 de-identified sample items (metadata + 2 frames each)
├── eval/
│   ├── run_eval.py      # stance accuracy/P/R/F1 + confusion matrix + P/R set F1
│   └── README.md        # gold.csv format; gold set still being labeled
└── requirements.txt
```

## 3. Data locations (outside git)

- Research corpus: `D:/ua_data/results/<aweme_id>/v.json` (one record per analyzed clip; raw video
  deleted after analysis, previews in `D:/ua_data/previews/`).
- Web viewer + full table: https://banford74.github.io/Gameclip-SNA/ ·
  `data/clips.csv` in the repo root (2201 rows: 1053 target + 1148 deprioritized legacy).
- **Do not commit** secrets, API keys, raw videos, or anything under `D:/ua_data/`.

## 4. Coding scheme (the part that must not drift)

Content stance — **4 classes only**:

| label | meaning | examples |
|---|---|---|
| `positive` | clip conveys positive emotion / admiration / hype | 高光、燃、暖心、安利 |
| `negative` | clip conveys negative emotion (frustration, failure, complaint) | 翻车、恐怖氛围、吐槽 |
| `neutral` | informational/instructional, no strong emotion either way | 攻略、版本说明、纯展示 |
| `mixed` | positive and negative are **co-present or reversed within the clip** | 先惨后爽、反差打脸、社死名场面 |

- `mixed` is about **structure**, not intensity. "情绪很强烈" ≠ mixed. A funny failure clip is
  usually `mixed`; a pure complaint is `negative`.
- **Comments/Task B have no 4-class at all** — never apply these labels to comments, and never let a
  comment field appear in this schema.

P-codes: 20 codes (P101–P120), each hit must carry frame/second evidence (`"f_04 12s"` style).
Empty `p_codes` is allowed **only** when no code fits (5.0% in the labeled corpus; if you see a
systematic jump above ~10%, suspect prompt/codebook drift). R-codes: 96 (R1–R9 groups), hits only.

Confidence: 0–1, model-stated; do not clamp or invent it.

## 5. Model & request conventions

- Model: `deepseek-v4.1-flash` on OpenCode Go (`https://opencode.ai/inference/go/openai/v1/chat/completions`;
  override with `OPENCODE_BASE_URL` / `OPENCODE_MODEL`); key comes from `OPENCODE_API_KEY` **env**, never a file.
  The Go endpoint requires an `x-opencode-session` header — `src/extract.py` sends one per process
  (`OPENCODE_SESSION` overrides); omitting it returns `400 MissingSessionID`.
- **JSON mode is mandatory**: `response_format={"type":"json_object"}`; prompt-only JSON is not allowed.
- temperature 0.3 · max_tokens 4000 · ≤20 frames per request (512 px, ~1 frame / 2 s).
- Validation failures → repair round (re-ask with the error list), max 2; log every attempt with
  tokens and ms. Never silently accept an off-schema record.

## 6. Commands

```bash
python src/run.py data/samples -o out/ --mock     # offline smoke test (<1 s)
python src/run.py data/samples -o out/            # live (needs OPENCODE_API_KEY)
python src/robustness.py                          # must print "validation failures: 0"
python eval/run_eval.py eval/gold.csv out/rows.csv
```

## 7. Guardrails (already implemented — keep them)

- Writes are restricted to the `--out` directory, which must stay under the working directory.
- Per-item wall-clock timeout + bounded workers (max 8); one bad item must never abort the run.
- A bad input (empty title+frames, no frames, bad duration) is skipped with a logged reason.
- Cap frames at 20 and per-frame bytes at 512 KB to bound token cost.

## 8. Evaluation status

- Gold set: **in progress** (≥30 hand-labeled rows, `eval/gold.csv`; never shown to the model).
- When it lands: fill `eval/RESULTS.md` with metrics table, confusion matrix, error analysis
  (N errors → cause → fix), one ablation with a measured delta, and a reproducibility note
  (model, temp, prompt path, date).
- Do **not** claim numbers that are not in a RESULTS file with a date.

## 9. Style / conventions

- Python 3.11+, stdlib + `requests` only (no heavy deps); `mcp` only for the optional MCP server.
- Chinese prompts, English code/comments. Evidence strings are Chinese and must cite frames/seconds.
- Keep `src/codebook.json` in sync with the research codebook (`pipeline/ua_agent/pr_codebook.py`);
  expanded codes P116–P120 (music/dance, tutorial, daily vlog, unboxing, collab-announcement) and
  R356/R814/R310/R907/R456 were added in the codebook-evolution round — do not drop them.
