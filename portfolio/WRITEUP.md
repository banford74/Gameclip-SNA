# Design writeup — GameClip Codebook

**Problem.** Creative strategy research on short game videos needs labels that are (a) *comparable*
across thousands of clips and (b) *checkable* against the pixels. Free-form model commentary is
neither. So the unit of work is a **validated record per clip**: content stance (4-class), plot-layer
codes (P), visual-feature codes (R), all with frame evidence, plus a stated confidence — the codebook
expressed as a schema, then produced by an agent and later scored by humans.

**Schema and why it looks like this.** `content_sentiment.label` is a 4-way enum because the research
question is "what does the clip *mean* emotionally", and `mixed` is a real, designable structure
(先抑后扬 / 反差打脸) that a 3-class scheme would erase. Intensity (1–4) is separate from the label:
"情绪强烈" and "正负并置" are different phenomena, and conflating them was a documented failure mode.
P-codes (20, multi-select with per-hit evidence) are the narrative skeleton; R-codes (96, hit lists)
are the visual features. Evidence is *required on P hits* because it makes the label falsifiable —
a reviewer can jump to `f_04 12s` and disagree. Confidence is model-stated and logged, never clamped,
so it can be calibrated later. `additionalProperties: false` keeps the schema closed: an extra field
from the model is a bug, not a bonus.

**Architecture** (one item flows left→right; failures exit with a logged reason):

```
item.json ─► build_prompt ─► LLM (JSON mode, ≤20 frames)
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
              json.loads fails        validate() errors
                    │                       │
                    └──── repair round ◄────┘   (re-ask with error list, ≤2)
                                │
                        valid record ─► rows.csv + logs.jsonl
```

The batch layer (`run.py`) runs a bounded thread pool, imposes a per-item wall-clock timeout, writes
only under `--out`, and never lets one bad item abort the run. The **extension** is an MCP server that
exposes the labeled corpus (`data/clips.csv`) as tools — `list_clips`, `get_clip`, `codebook_stats` —
so an agent can *query real labels* instead of hallucinating them; it reuses the same schema vocabulary.

**Key decisions and trade-offs.**

1. **JSON mode + validation + repair, not "prompt and pray."** In the pre-JSON-mode pipeline, 9 of 1482
   returned records were unparseable (~0.6%); each cost a human a manual re-check. JSON mode makes the
   wire format an object by construction, and the validator catches the semantic failures JSON mode
   cannot (unknown codes, missing evidence, extra fields). The repair round converts most failures into
   valid records for one extra call — worth it because a rejected item costs more downstream than a
   retry. Cost: the validator must be maintained in lockstep with the schema; drift between them is
   the main risk.
2. **Frames, not video, and a 20-frame cap.** Twenty 512-px frames ≈ 4.7k input tokens and works for
   fast-cut clips (samples are ≤60 s by construction). Trade-off: very fast edits can lose events
   between frames; the evidence requirement makes that visible (evidence can't cite a moment that
   isn't sampled) rather than hidden.
3. **The codebook evolves; the schema doesn't.** The original 15 P-codes were buy-ad-shaped; the 2026
   corpus is dominated by tutorials, daily vlogs, music/dance and collab announcements. A
   harvest → propose → review → activate loop added P116–P120 and five R codes. Result: no-P share fell
   from 23.5% to **5.0%**, with the new codes (P118 260, P117 195, P116 175) among the most frequent —
   evidence the gap was real, not prompt noise. Trade-off: old labeled items lack the new codes; any
   before/after comparison must be re-run on both codebooks (that is the planned ablation).
4. **Skip loudly, never fail silently.** Empty items, missing frames, bad durations are `skipped:` rows
   with a reason; off-schema model output is a failed attempt that gets repaired. The `robustness.py`
   harness pins this behaviour with 10 adversarial cases (injection, refusal, invalid JSON, empty
   input, 30 frames, negative duration, …), so a regression is caught offline, at zero API cost.
5. **De-identified samples in-repo.** Three real items ship with two frames each; author handles are
   masked. The corpus itself stays out of git (it links to public platform URLs only).

**Limitations.** The gold set is still being labeled — until it lands there is no defensible accuracy
number, only reliability and coverage statistics. OOD generalization is asserted from codebook coverage
(光遇 208 clips, 0 with no P-code), not from a held-out metric yet. One video = one call means a
2-minute clip and a 5-second clip cost the same, which is wasteful at the low end. The free-tier model
quotas make large batches fragile in practice (bounded retries, then skip).

**With one more week.** Label the 30–50 item gold set (4-class stance + P/R), run `eval/run_eval.py`,
and report per-class recall plus a confusion matrix — the stance enum's real risk is `mixed` being
under-predicted, and a matrix is the only way to see it. Then run the codebook ablation (v1 vs v2 codes
on the same gold items) and a calibration slice (does 0.9 confidence mean 90% correct?). If the eval
holds, the next engineering step is caching frame embeddings so a re-label run only re-prompts changed
items — the 47 s/item cost is dominated by re-sending images.
