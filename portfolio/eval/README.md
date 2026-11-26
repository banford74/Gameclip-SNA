# Evaluation — gold set in progress

The gold set is being hand-labeled (target ≥30 items, 4-class stance + P/R codes).
Until it lands, `eval/` contains only the scorer.

## Format (`eval/gold.csv`)

| clip_id | stance | p_codes | r_codes |
|---|---|---|---|
| 7651122046423835377 | positive | P116 | R801;R811 |
| 7693578360249480794 | mixed | P101;P112 | R101;R452 |

- `stance` ∈ positive / negative / neutral / mixed (content stance only — no comment/mixed confusion; comments have no 4-class at all)
- `p_codes` / `r_codes`: semicolon-joined; empty allowed
- Labels are held out — never shown to the model.

## Run

```
python eval/run_eval.py eval/gold.csv out/rows.csv
```

Reports: stance accuracy, per-class precision/recall/F1, macro-F1, confusion
matrix, plus micro-F1 and exact-match for P-code and R-code sets.

## Planned analyses (fill `RESULTS.md` when the gold set is ready)

- error analysis table: N errors → cause → fix
- one ablation with a measured delta (e.g. codebook v1 vs v2, or frames 8 vs 20)
- calibration: bucket by stated `confidence` and check whether 0.9-confidence items are ~90% correct
