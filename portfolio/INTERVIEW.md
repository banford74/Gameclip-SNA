# INTERVIEW.md — 15 canonical agent questions, answered for this project

Answers are grounded in the GameClip Codebook tool in this repo where possible.

**1. Agent loop / ReAct.** An agent is a loop around an LLM: observe → reason → act (tool call) →
observe the result, repeated until the goal is met or a budget is hit. ReAct is the pattern where the
model interleaves an explicit thought with an action, so the trace shows *why* the next tool call
follows. A chatbot answers once and stops; an agent owns the control flow — it decides when to call a
tool, reads the result, and decides again. In this project the "agent" is deliberately narrow: one
extraction call per item, plus a repair loop when the output fails validation — that loop is the same
control structure (act, observe, decide) at a smaller scale.

**2. Tool / function calling.** The model emits text; "calling" a tool means the *runtime* parses a
structured tool call (name + JSON arguments) out of the model's output, executes the function locally,
and feeds the result back as a message. The model never runs code — the harness does. That is why
tool schemas (names, argument types, descriptions) matter as much as the prompt: they are the API the
model programs against. In my extractor, the "tool" is implicit (one JSON-mode call), but the MCP
server exposes real tools — `list_clips`, `get_clip`, `codebook_stats` — whose return values an agent
can consume as observations.

**3. MCP.** The Model Context Protocol standardizes how a host (Claude Code, etc.) discovers and calls
external tools/data over a simple client–server protocol, so one tool server works across hosts. It
solves the N×M integration problem: without it, every agent product needs its own integration for
every data source. I'd add a tool when the agent needs *fresh, authoritative* data (a DB, an API) or
when the result must be reproducible outside the model's weights; I would not add one for static
knowledge or for anything the model already does reliably in-context. This repo ships a minimal MCP
server over the labeled clip corpus for exactly that reason.

**4. Reliable structured output.** Use the API's JSON mode (or tool-calling with a schema) so the
wire format is guaranteed parseable, then validate *semantics* on the client: enum membership, required
fields, codebook membership, evidence presence, no extra fields. When it fails: log the raw output,
re-ask once or twice with the concrete error list, and if it still fails, quarantine the item — never
accept a partially valid record. In this project JSON mode + validation + 2 repair rounds moved
unparseable output from ~0.6% (prompt-only) to 0 on the target set.

**5. Subagents / multi-agent.** A subagent helps when a sub-job is read-heavy and can be *isolated* —
e.g. "read these 40 long transcripts and give me only the timeline" — because it keeps the parent's
context small and lets the sub-job use its own prompt/tools. It hurts when the work is short (fixed
overhead), when the subagent needs the parent's full context (lossy handoff), or when the task is
sequential (no parallelism). The tradeoff is context isolation vs. information loss. My codebook loop
is the same idea one level up: an LLM reviewer proposes code changes from error clusters, and a human
activates them — the reviewer sees a digest, not the whole corpus.

**6. Context window.** The context is the model's working memory: system prompt, tools, history,
tool results, and the current turn. As it fills, quality degrades (lost-in-the-middle, attention
dilution) and *cost grows superlinearly in practice* because every step re-sends the prefix unless it
is cached. That is why compaction (summarize old turns) and selective retrieval matter. In extraction
this is why I cap frames at 20 and keep the codebook prompt compact (~4.7k tokens with 20 frames)
instead of dumping every code definition in full.

**7. Cost/latency without quality loss.** First measure: tokens in/out and wall-clock per item. Then
attack the biggest term. Here: images dominate input (20 frames ≈ 4.7k tokens), so fewer/cheaper frames
for easy items, batching, and prompt caching of the fixed codebook prefix are the levers. Output tokens
dominate too (~7.9k — the model writes a long report), so a compact schema-only output is a 3× saving.
Route easy items to the cheap model and escalate only on low confidence; cache identical inputs; run
with bounded concurrency (5 workers ≈ 6.2 items/min, measured).

**8. Reproducibility.** Pin the model id, temperature, max_tokens, the prompt file path, and the
codebook version; log per-attempt usage and timings; record the run date. Keep the input manifest
under version control and make results derivable from it. Anything not pinned is not an experiment —
"the model got better" is unfalsifiable without a fixed config. In practice: same prompt file, same
JSON schema, same codebook JSON, `logs.jsonl` carrying tokens/ms per attempt.

**9. Stopping dangerous/irreversible actions.** Layered: least-privilege tools (no network/file access
unless needed), a sandbox for file writes, permission prompts for anything destructive, and
human-in-the-loop for irreversible operations. Hooks (pre/post tool) are the enforcement point —
deny by policy, not by prompt. My batch tool writes only under `--out`, refuses paths outside the
working directory, and has per-item timeouts; the pipeline deletes raw videos only after the derived
record is safely written.

**10. Hallucination in extraction.** Make evidence mandatory and anchored (frame/second), then verify:
does the cited frame exist in the sampled set, does the code exist in the codebook, does the stance
label agree with the stated evidence? Sample-audit the highest-confidence and lowest-confidence
records — they fail differently. Calibrate confidence against human labels so the model's "0.9" is
actually ~90%. The 5.0% no-code rate is a useful canary: an unexplained jump means the model is
inventing codes or the prompt drifted.

**11. "Passed the test" by weakening it.** Watch for test edits in the same change as code changes,
pass rates that jump for no reason, and assertions that became weaker (skip/xfail, tolerance widening,
gold labels edited). The lesson: the eval must be versioned and separate from the code under test, and
changes to it need their own review. In my project the gold set is held out and never shown to the
model — if a model ever saw it, every number becomes a leak, not a measurement.

**12. Evaluating an agent.** For this task: build a gold set of ≥30 clips hand-labeled by a human
(4-class stance + P/R codes), never shown to the model; then report stance accuracy, per-class
precision/recall/F1, a confusion matrix, and micro-F1/exact-match on the code sets. Choose metrics that
match the cost of errors: a wrong `mixed` matters more than a missing R-code, so class-level numbers
beat a single accuracy. Add a reproducibility note and an error-analysis table so the number is
actionable.

**13. 82% accurate — improve and prove it.** Read every error and categorize first: label ambiguity,
codebook gaps, missing visual evidence, prompt ambiguity. Fix the dominant cause, then re-run the *same*
gold set and report the delta per class. One change at a time (ablation): e.g. codebook v1 vs v2 on
identical items, or 8 vs 20 frames. Reject a "fix" that only moves the aggregate while a class gets
worse — that's usually threshold-tuning in disguise.

**14. Prompt vs RAG vs fine-tuning.** Prompt when the task is expressible in instructions and the
knowledge fits in-context; RAG when the knowledge is large, changing, or must be cited; fine-tuning
when the *behaviour* (format, style, domain conventions) is stable and volume justifies training —
fine-tuning is bad at injecting fresh facts. For this project: prompt + codebook covers the task
today; a codebook that keeps growing (now 20 P + 96 R codes) eventually argues for fine-tuning the
tagging behaviour, which is exactly the next research step.

**15. STAR — an agent I built.** Situation: research on short game videos needed thousands of
comparable labels; manual coding didn't scale and free-form LLM commentary wasn't scorable. Task: build
an extractor that turns one video into a validated 4-class-stance + P/R-code record, reliably enough to
run over a corpus. Action: JSON-mode calls with a closed schema, a validator + 2-round repair, a
frame-sampling budget, a skip-with-reason policy, and a robustness harness; then a codebook-evolution
loop (harvest → propose → review → activate) that added five P codes and five R codes. Result: 1049/1053
clips labeled with 0 unparseable records, no-P share down from 23.5% to 5.0%, ~6.2 items/min with 5
workers, and a gold-set scorer waiting for labels. One hard bug: a lock held across logging deadlocked
the batch at item ~40 — fixed by making the lock reentrant and moving logging outside the critical
section.
