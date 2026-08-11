# The optimization loop

Budget this at 10–100 model calls. Anything needing hundreds of scored rollouts,
a surrogate model, or a training set belongs in DSPy, not here.

## Loop

```
1. Run current prompt on the training split.       (n calls)
2. Score with spec.json. Keep the full failing output, not just the score.
3. Diagnose: read the failures, write what went wrong in prose, first.
4. Propose 2-3 distinct candidates addressing the diagnosis.
5. Score each. Keep survivors on a Pareto frontier (below).
6. Stop when no candidate improves for two rounds, or budget is spent.
7. Score the winner on the HOLDOUT. Report that number, not the training number.
```

## Diagnose before proposing

Write the diagnosis in natural language before writing any new prompt text. Feed
the model the actual failing outputs, the assertion that failed, and the reason
string — not a summary. A diagnosis grounded in real failure text produces
targeted edits; a diagnosis from a score alone produces vague rewording.

This is the core idea behind reflective prompt evolution (GEPA, ICLR 2026), which
beat both RL and Bayesian prompt search with ~35× fewer rollouts precisely because
the feedback channel is rich text rather than a scalar.

## Keep a Pareto frontier, not the best average

The naive loop keeps the highest-mean candidate each round and collapses to a
bland prompt that is mediocre everywhere. Instead keep any candidate that is the
best on **at least one case**, even if its average is worse. Sample parents from
that frontier.

Store it as a small JSON file:

```json
[{"id": "c3", "prompt_file": "cand3.txt", "per_case": {"c-001": 1, "c-002": 0},
  "notes": "fixed the length conflict; still fails on empty input"}]
```

## Candidate strategies, cheapest first

1. **Fix audit defects.** Contradictions and rule-violating examples. Frequently
   the whole gap. Always try this alone as candidate #1 — it is the honest
   baseline for whether anything cleverer is needed.
2. **Bootstrap few-shot demos.** Run the current prompt, keep the outputs that
   pass every assertion, paste 3–5 of them back in as examples. Highest measured
   gain-per-call of any technique in this family, and it needs no labeled data
   when your assertions are the filter. Check the mined examples for diversity
   before pasting — mining five near-identical winners teaches a template.
3. **Restructure.** Long context to the top, query last, one output contract,
   consistent delimiters. No wording change.
4. **Targeted single-defect edits.** One change per candidate so the diff
   attributes cleanly. Bundling five edits into one candidate tells you nothing
   about which one worked.
5. **Reword.** Last, and least effective. Prompt quality is mostly structure and
   specification, not phrasing.

## Every candidate ships finished

A rewrite is not allowed to contain placeholders — `[paste example here]`,
`{topic}`, `<fill in the constraint>`. If the rewrite needs content you do not
have, either bake in a defensible default or write an explicit instruction for the
model to request it at runtime. A prompt with an unfilled blank is a prompt that
fails on first use, and audit.md H1 flags exactly that defect in prompts you
review — do not introduce it in the ones you write.

When generating candidates, include the trajectory so far — every prompt tried,
its score, and the diagnosis — sorted worst to best. The model uses the gradient.
Ten rounds is plenty; the published method runs hundreds, and the returns past ~10
do not justify the calls at this scale.

Keep it in one file the loop appends to. It doubles as the audit trail for what
you tried and why.

## Scoring without a labeled set

If there is no ground truth, compare candidates **pairwise** with a judge:
present output A and output B for the same input, ask which better satisfies one
named criterion, and **run each pair twice with the order swapped**. Position bias
is large enough to invent a winner on its own. Discard pairs where the two orders
disagree — that is a tie, not a signal.

At ~5 candidates × ~10 cases × 2 orders = 100 judgments, a plain win-rate table is
enough. Skip bandit allocation at this scale.

Say clearly in the report that pairwise-judge results are relative preference, not
correctness.

## Compression

Only after quality is right.

1. Delete duplication — restated checklists, rules stated twice. Free.
2. Cut rules that never bind (see audit E3). Nearly free.
3. Telegraphic rewording. This is where behavior starts to drift.

Re-run the full diff after every compression step. Treat ~2–3× reduction on
instruction text as the ceiling; the compression research showing 5–20× with
minimal loss is compressing *context and demonstrations*, not instructions, and
reasoning-heavy tasks degrade well before similarity metrics notice.

Report tokens saved against the smallest historical version, not the previous one.

## Stopping

Stop when any of:
- two consecutive rounds produce no candidate that beats the incumbent
- remaining failures are all "criterion not actually defined" (go back to Phase 2)
- the holdout score stops tracking the training score — that is overfitting, and
  more rounds make it worse

## Reporting

Always include:
- mode (AUDIT / GROUNDED / MEASURED) and case count
- holdout pass rate before and after, per assertion
- what changed, as a list of edits tied to the failure category each addressed
- what did **not** improve, and what remains unmeasured
- token delta

Never report a training-split number as the result. Never report "looks better".

## Not worth building here

- Bayesian instruction search (MIPROv2) — needs 200+ labeled examples and 40+
  trials to beat random search. Below that it fits noise. Its *instruction
  proposer* — grounding candidate generation on a dataset summary plus mined
  demos — is worth imitating; the surrogate model is not.
- Evolutionary population methods (PromptBreeder) — thousands of calls.
- Textual-autodiff frameworks (TextGrad) — a computation graph is infrastructure.
  Flat critique-and-revise gets most of the benefit.
- Learned compressors (LLMLingua) — requires shipping a local model.
- Anything with weight updates.
