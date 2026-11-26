# 3-minute demo — slides + script

## Slide 1 — Problem (20 s)

**Short game videos need scorable labels, not commentary.**
- Research corpus: 1,053 clips (2026, ≤60 s, like-ranked per game; 7 train + 2 OOD games).
- Annotation codebook: 4-class content stance + 20 P-codes (plot) + 96 R-codes (visual).
- Free-form LLM text can't be scored; manual coding doesn't scale.

## Slide 2 — The tool (20 s)

**One item in → one validated record out.**
- `src/schema.json` = codebook in code (closed schema: enum stance, code membership, evidence, 0–1 confidence).
- **JSON mode** call → client-side **validation** → **repair round** (re-ask with the error list, ≤2).
- `python src/run.py data/samples -o out/` — one command, bounded workers, per-item timeout, writes only under `out/`.

## Slide 3 — Live run (30 s)

```bash
$ python src/run.py data/samples -o out_live --limit 1
items=1 workers=1 mock=False -> out_live
ok=1 skipped=0 failed=0 total=1 in 9.7s
```

`out/rows.csv` row: `7651122046423835377, ok, positive, 2, "标题与标签…；0-27.7s 未见负向证据", P116, "", 0.4, "百里守约向音乐卡点…", 1, 9715`
— and `logs.jsonl` carries per-attempt ms/tokens/validation errors.

## Slide 4 — Evidence it works (30 s)

| Metric | Value |
|---|---|
| Unparseable records, prompt-only JSON | 9 / 1482 (0.6%) |
| After JSON mode + validate + repair | **0** on the 1,053-clip target set (1,049 parsed; 4 videos deleted by platform) |
| No-P-code share (codebook coverage) | **5.0%** (was 23.5% with the original 15 P-codes) |
| Cost / latency per item | 4.7k prompt + 7.9k completion tokens · 47.7 s wall |
| Throughput | 5 workers ≈ 6.2 items/min |
| Robustness harness | 10/10 adversarial cases end in ok / skip-with-reason |

## Slide 5 — The failure I found + next (30 s)

**Failure:** the live sample came back `confidence 0.4` with `P116` (music/dance) and **zero R-codes** —
a truthful but weak label. The model is hedging on stylized edits it can't map to the visual codebook.
**Fix path:** gold set ≥30 → per-class recall + confusion matrix (expect `mixed` under-predicted) →
codebook ablation (v1 vs v2 codes on the same items) → calibration buckets.
**Then:** frame-embedding cache so re-labels don't re-send images.

---

## 3-minute narration (say it, don't read it)

1. **(0:00–0:30)** "This is a structured-extraction agent for short game videos. One video goes in; one
   validated record comes out — a 4-class content stance, plot codes and visual codes with frame
   evidence, and a confidence. It exists because free-form model commentary can't be scored, and the
   research needs thousands of comparable labels."
2. **(0:30–1:15)** "The codebook is the schema: a closed JSON schema, JSON-mode calls so the wire
   format is an object by construction, a client-side validator, and a repair round that re-asks with
   the error list. Here's the whole run — one command, three items, under a second in mock mode and
   ~10 seconds live for one item."
3. **(1:15–2:00)** "Does it hold up? In the earlier prompt-only pipeline, nine of fourteen hundred
   returned records were unparseable; after JSON mode plus validation plus repair, zero on the
   thousand-clip target set. And coverage improved because the codebook evolved — no-plot-code share
   fell from 23.5% to 5.0% after adding five P-codes the old buy-ad codebook was missing."
4. **(2:00–2:30)** "The interesting failure: on a stylized edit the model gave P116, no R-codes, and
   confidence 0.4. That's honest — it can't map the edit to the visual codebook. That's exactly what
   the gold set is for: measure per-class recall and the confusion matrix, especially for `mixed`."
5. **(2:30–3:00)** "Next: the 30-item gold set, the codebook ablation, and calibration. Repo, schema,
   robustness harness, MCP server over the corpus — all in the repo. The number I want to defend is
   stance F1 per class, not a vague 'it works well'."
