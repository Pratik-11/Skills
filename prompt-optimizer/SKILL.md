---
name: prompt-optimizer
description: Audit and optimize LLM prompts with measured evidence — never claims an improvement it did not measure. Finds rules that contradict each other, examples that violate the prompt's own constraints, and stale API patterns; builds an eval set from real failures; rewrites; then proves the new version is better with a before/after diff. Use whenever the user wants to improve, optimize, audit, review, fix, tighten, shorten, compress, debug, evaluate, A/B test, or measure a prompt or system prompt — trigger phrases include "optimize this prompt", "improve my prompt", "review this system prompt", "why is this prompt inconsistent", "make this prompt cheaper", "is this prompt over-engineered", "test my prompt", "compare these two prompts" — or when a prompt produces inconsistent, hallucinated, over-long, off-format, or contradictory output.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/*), Read, Write, Edit, Grep, Glob
---

# Prompt Optimizer

## The one rule

**Never report an improvement you did not measure.**

Rewriting a prompt feels productive and proves nothing. The common failure — seen
in real prompt archives — is a dozen versions shipped in a week, each described as
better, none tested, with contradictions quietly accumulating the whole time. If
you cannot measure, say so in the same breath as the rewrite.

State the mode in every report:

| You have | Mode | You may claim |
|---|---|---|
| The prompt only | **AUDIT** | "Fixed N specific defects." Never "it performs better." |
| Prompt + real outputs | **GROUNDED** | "N% → M% on checks derived from the observed failures." |
| Prompt + labeled examples | **MEASURED** | "N% → M% on a held-out set of K cases." |

Upgrade the mode when you can. Getting 20 real outputs takes one command and moves
you from AUDIT to GROUNDED — always ask for them before settling for AUDIT.

## Workflow

Route by what the user has. Phase 1 always runs. Stop after any phase if that
answered the question.

### Phase 1 — Audit (always)

Mechanical pass first, it is free:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/lint.py PROMPT_FILE
```

Then read the prompt yourself for what a script cannot see, using
[references/audit.md](references/audit.md) as the catalog: semantic
contradictions, buried instructions, underspecified edge cases, rules that cannot
bind, examples teaching the opposite of the rule.

Report findings as a ranked list with line numbers and the concrete fix. Do not
rewrite yet — the user may only want the audit, and an unrequested rewrite
destroys the baseline you need for Phase 4.

### Phase 2 — Ground the evaluation

Skip only if the user has no outputs and refuses to produce any.

Follow [references/evals.md](references/evals.md). The order matters and it is
the opposite of most people's instinct:

1. **Do not ask what "good" means up front.** Users cannot specify criteria in the
   abstract; they recognize problems when shown output. Ask for outputs, not rules.
2. **Read real outputs and write free-form notes** on what is wrong (open coding).
   20 outputs is a useful floor; 100 is where categories stop appearing.
3. **Cluster notes into a failure taxonomy**, then count each category. Fix by
   frequency, not by which is most interesting.
4. **Most "failures" are unspecified requirements**, not model errors. If the
   prompt never stated the rule, that is a Phase 1 spec bug — fix it there and
   requeue, do not build an eval for it.
5. **Convert the persistent categories into assertions.** Deterministic check if
   code can decide it; binary LLM judge only if it genuinely cannot.
6. **Split the cases.** ~70% the optimizer sees, ~30% held out and never shown to
   it. Report final numbers on the holdout only.

Write the assertions to `spec.json` and the cases to `cases.jsonl`.

### Phase 3 — Rewrite

Follow [references/optimize.md](references/optimize.md). In short: diagnose from
actual failing outputs before proposing anything, produce 2–3 distinct candidates
rather than one, and keep a candidate that wins on any single case even if its
average is worse — the best-average-only rule collapses to bland prompts.

Cheapest effective moves, in order:
1. Fix the Phase 1 defects. Often this alone closes most of the gap.
2. Add few-shot examples mined from the prompt's own passing outputs.
3. Restructure (long context to the top, query last, one output contract).
4. Only then reword.

### Phase 4 — Prove

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/check.py spec.json baseline.jsonl --compare candidate.jsonl
```

Report the verdict verbatim, including `MIXED` and `REGRESSED`. A rewrite that
moved nothing is a real and useful result — say so rather than reaching for
qualitative praise.

Watch for Goodhart: a candidate can pass a "name at most 3 services" check by
saying almost nothing. Any check that improves while output volume drops needs a
human look before you count it as a win.

## Scripts

Both are stdlib-only Python, no install, no network, and both self-test:

| Script | Does | Verify |
|---|---|---|
| `scripts/lint.py` | Static defects: constraint conflicts, examples violating stated limits, allow/forbid collisions, stale API patterns, unbalanced tags, duplicate rules, missing output contract | `python3 scripts/lint.py --selftest` |
| `scripts/check.py` | Scores outputs against assertions; `--compare` diffs two versions; `--export-promptfoo` emits a config | `python3 scripts/check.py --selftest` |

`check.py --help` lists the assertion types. If `promptfoo` is installed the user
may prefer it as the long-term harness — export the config and hand it over. Do
not require it.

## References

- [references/audit.md](references/audit.md) — defect catalog for the manual pass
- [references/evals.md](references/evals.md) — error analysis, assertions, judge design and validation
- [references/optimize.md](references/optimize.md) — candidate generation, scoring, selection, stopping
- [references/patterns.md](references/patterns.md) — current model guidance and deprecated patterns to flag

## Your own failure modes

- **Rewriting when asked to audit.** Findings first. The unmodified prompt is the baseline.
- **Claiming a win from a clean rewrite.** A tidier prompt is not a better one.
- **Asking for success criteria before showing outputs.** It does not work; harvest criteria from reactions to real output.
- **Building an LLM judge for something `regex` decides.** Deterministic checks are free, stable, and need no validation.
- **Reporting numbers from cases the optimizer trained on.** Holdout or no number.
- **Compressing before it works.** Get quality right, then cut tokens and re-run the diff. Treat ~2–3× reduction on instruction text as the ceiling.
