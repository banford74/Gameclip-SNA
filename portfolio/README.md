# GameClip Codebook — structured extraction for short-game-video creative analysis

**What:** a one-command extractor that turns one short game video (metadata + sampled frames) into a
validated, schema-checked record: **4-class content stance** (`positive / negative / neutral / mixed`),
**P-codes** (plot layer, multi-select, each with frame evidence), **R-codes** (visual feature hits),
and a **0–1 confidence** — the codebook itself is the schema.
**Why:** creative/广告素材 analysis needs a *measurable* label space, not free-form commentary.
This repo makes the annotation machine-readable so downstream work (style analysis, OOD generalization,
model fine-tuning) can score it — and it ships the honesty layer: schema enforcement, retry/repair,
a robustness harness, and an eval scorer waiting for its gold set.

> Part of a larger research project (game short-video dataset, Task A only). Task B (comment VAD) is
> out of scope for this repo. Generated from the course project; the full corpus and the web viewer
> live at https://banford74.github.io/Gameclip-SNA/.

## Run

```bash
pip install -r requirements.txt
export OPENCODE_API_KEY=...            # OpenCode Models key; any OpenAI-compatible endpoint also works via OPENCODE_BASE_URL
python src/run.py data/samples -o out/            # live: one API call per item, JSON mode
python src/run.py data/samples -o out/ --mock     # offline demo, deterministic, no API cost
python src/robustness.py                          # 10 messy/adversarial inputs, offline
python eval/run_eval.py eval/gold.csv out/rows.csv   # scoring (gold set in progress)
```

Each item JSON: `{"video_id", "title", "author", "duration_s", "frames": ["path/to/f_01.jpg", ...]}`
(frames are sampled ~1 per 2 s at 512 px; `data/samples/` has three real examples).

Outputs: `out/rows.csv` (one row per item) + `out/logs.jsonl` (per-attempt: ms, tokens, validation errors).

## Design (1 paragraph)

The schema lives in `src/schema.json` and in `src/extract.py:validate()` — an enum stance, P/R code
membership, evidence-string requirements, and `additionalProperties: false`. The model is called in
**JSON mode** (`response_format={"type":"json_object"}`), so the wire format is a JSON object by
construction; the validator then checks *semantics* (unknown codes, missing evidence, extra fields).
On any parse or validation failure the extractor re-asks with the error list (**repair rounds**, max 2)
and logs every attempt — the loop stops at the first fully valid record. Failures are per-item:
a bad input (`empty`, `no frames`, `bad duration`) is skipped with a reason, never wedges the batch.
The one extension is an **MCP server** (`src/mcp_server.py`) that exposes the labeled corpus
(`data/clips.csv`: 1053 target clips + 1148 deprioritized legacy rows) as tools — `list_clips`,
`get_clip`, `codebook_stats` — so an agent can query real labels instead of guessing.

## Results

**Structured-output reliability** (production runs, `out/logs.jsonl` style): with prompt-only JSON
(the pre-JSON-mode pipeline) **9 of 1482** returned records came back unparseable (0.6%); after
switching to JSON mode + validation + repair, the sample live run and the 1050-item target set
produced **0** unparseable records (`1049/1053` items parsed; the other 4 videos were no longer
retrievable from the platform).

**Dataset scale** (the corpus this tool label-generates): 1053 clips — 794 training + 259 OOD —
all published in 2026, ≤60 s, like-ranked per game. Codebook coverage: **无 P 码 5.0%** (53/1049),
down from 23.5% with the original 15-code plot layer; top P codes after the codebook-evolution round:
P118 (daily-vlog) 260, P105 235, P114 228, P101 228, P117 195, P116 (music/dance) 175.
Cost/latency: mean 4.7k prompt tokens (20 frames @512 px) + 7.9k completion tokens, 47.7 s/item
wall-clock; 5 workers sustain ~6.2 items/min.

**Gold-set metrics: pending** (`eval/` — scorer + format are ready; labels held out).

## Reproducibility

Model: `deepseek-v4.1-flash` via OpenCode Models (`https://opencode.ai/inference/openai/v1`, JSON mode) · temperature 0.3 · max_tokens 4000 · prompt in
`src/extract.py:build_prompt()` · codebook `src/codebook.json` (20 P / 96 R) · runs logged per attempt
with tokens and ms. Gold-set scoring: `eval/run_eval.py` (stance accuracy, per-class P/R/F1,
confusion matrix, P/R micro-F1).

## Limitations & next steps

- Gold set (≥30 hand-labeled) is the immediate next step; until then there is no "F1 0.81" sentence.
- One video = one API call; long clips are sampled to 20 frames, so fast-cut edits can lose events.
- Free-tier model quotas (429s) are handled by bounded retries, but a batch of thousands needs a
  paid key or a local model.
- Codebook evolution is human-approved today (`data/codebook_loop` in the research repo); automating
  the "propose → review → activate" loop is the next research step.
