# Building the evaluation

The goal is a small set of checks that fail when the prompt gets worse. Not a
benchmark — a regression gate.

## Start from outputs, never from criteria

Asking "what does good look like?" up front does not work. People cannot specify
criteria in the abstract; they recognize problems when shown concrete output, and
their criteria shift as they look. This is documented (criteria drift, Shankar et
al., UIST 2024) and it is the single most common way an eval effort stalls.

So: ask for outputs. If none exist, run the prompt on real-shaped inputs and
produce some. Then show them and harvest reactions.

## Error analysis

**1. Open coding.** Read outputs one at a time and write a free-form note on
anything wrong. No taxonomy yet, no categories, no counting. Include the case ID.

**2. Axial coding.** Cluster the notes into failure categories. Name each one in
the user's vocabulary, not in ML terms.

**3. Count.** Tally per category. Fix by frequency. The interesting failure is
usually not the common one.

How many outputs: 20 is a usable floor for a first pass, 100+ is where you can
trust the distribution. Stop early only when ~20 consecutive outputs produce no
new category.

**4. Triage each category before building anything:**

- *The prompt never stated this requirement* → spec bug. Fix in the prompt now.
  This is most of them, and it needs no eval infrastructure.
- *The prompt states it and the model ignores it* → real failure. Build an assertion.
- *Reasonable people disagree whether it's wrong* → the criterion is not yet
  defined. Define it before measuring it.

## Mining prompt history for assertions

If the prompt is under version control, `git log -p` on it is an assertion source:
each edit encodes a requirement someone cared about. "v6 added a service cap" →
`max_occurrences` assertion. "v4 banned three-clause cascades" → a regex.

This works on any versioned prompt archive, including changelogs written in prose.
It is cheap and almost nobody does it.

## Writing assertions

**Deterministic first.** If code can decide it, code decides it. Deterministic
checks are free, stable, need no validation, and never drift. Reach for a judge
only for genuinely subjective properties.

Available in `scripts/check.py`: `regex`, `not_regex`, `contains`,
`not_contains`, `contains_all`, `contains_any`, `word_count`, `sentence_count`,
`is_json`, `json_keys`, `max_occurrences`, `no_repeat_ngram`.

Things people wrongly assume need a judge:

| Property | Deterministic check |
|---|---|
| Leaks internal identifiers | `not_regex` on the ID shape |
| Names too many entities | `max_occurrences` with a cap |
| Wrong length | `sentence_count` |
| Not valid JSON / missing fields | `is_json`, `json_keys` |
| Outputs read as templated | `no_repeat_ngram` across cases |
| Forbidden vocabulary | `not_regex` with an alternation |
| Wrong tense, banned openers | `not_regex` |

Write one assertion per failure category, with the category name as its `id`, so
the diff report reads as a list of the user's own problems.

## When you do need a judge

**Binary, not Likert.** Pass/fail beats 1–5. Scales create annotator variance and
need larger samples to detect a change.

**One criterion per judge.** A judge asked to score "quality" scores nothing.
Write several narrow judges instead.

Judge prompt shape:
- the task being judged, in one sentence
- exactly one criterion, with explicit pass and fail definitions
- 2–3 calibration examples near the boundary
- output constrained to one token or a small JSON object

Use a different (ideally stronger) model than the one being evaluated, and randomize
A/B order when comparing two outputs — position bias is large and consistent.

**Pairwise beats absolute.** "Which of these two is better on criterion X" is
measurably more reliable than "score this 1–5", and it is what you want anyway when
comparing two prompt versions.

## Validating the judge

An unvalidated judge is a random number generator with good manners.

1. Hand-label 50–100 outputs pass/fail yourself.
2. Run the judge on the same set.
3. Report **true positive rate and true negative rate separately.** Aggregate
   accuracy hides class imbalance — a judge that passes everything scores 90% on a
   90%-pass set.
4. If either rate is poor, fix the judge prompt before using it. Do not average
   the problem away.

Budget rule: a judge is worth its maintenance cost only past ~100 labeled examples.
Below that, use deterministic checks and read the outputs yourself.

## Test set construction

**Composition.** Cover the common path, the known edge cases, and one case per bug
ever found in production. Every new production failure earns a permanent case.

**Size.** 20 cases is enough to catch gross regressions. 100+ before trusting a
percentage. Report `n` next to every rate; "80%" on 5 cases is noise.

**Holdout.** Split ~70/30. The optimizer sees the 70. Final numbers come from the
30 only. Every optimization method overfits its eval set — without a holdout you
will confidently ship something worse.

**Two sets, different jobs.** A small curated CI set for regression gating; a
larger opportunistic set from production traffic for discovering new failures.

## Format

`spec.json`:

```json
{
  "assertions": [
    {"id": "no-internal-ids", "type": "not_regex", "value": "\\bi-[0-9a-f]{8,}\\b"},
    {"id": "length", "type": "sentence_count", "min": 2, "max": 4},
    {"id": "entity-cap", "type": "max_occurrences", "value": "\\b(Alpha|Beta|Gamma)\\b", "max": 3},
    {"id": "not-templated", "type": "no_repeat_ngram", "n": 4}
  ]
}
```

`outputs.jsonl` — one record per case:

```json
{"case_id": "cust-014", "output": "..."}
```

Keep `cases.jsonl` (the inputs) alongside so the run is reproducible. If the user
already runs promptfoo, `check.py --export-promptfoo` emits a starting config;
assertion types with no promptfoo equivalent are listed as a comment.
