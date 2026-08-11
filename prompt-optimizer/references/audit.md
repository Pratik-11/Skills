# Audit catalog

Defects to look for in the manual pass. `scripts/lint.py` covers A1, B1, F and
H1 mechanically — everything else needs reading. Report each finding as
`line — what's wrong — the fix`, ranked by how often it will bite.

## A. Contradictions

**A1. Numeric conflicts.** The same field given two limits ("35-70 words" in one
section, "30-70" in the schema, "30-45" in a checklist). The model satisfies none
of them reliably. Caught by the linter, but confirm the ranges actually govern the
same field before reporting — a title limit and a body limit legitimately differ.

**A2. Semantic conflicts.** Two instructions that cannot both hold, with no shared
vocabulary to make it obvious. "Be exhaustive" + "keep it under three sentences".
"Never mention internal tooling" + an example that mentions it. These are the
expensive ones; they need reading, and they are where most real prompt bugs live.

**A3. Scope-less exceptions.** A rule forbidden in one section and permitted in
another, far apart. Fix by moving the exception inline with the rule, not by
deleting one. Same-line exceptions ("never X unless Y") are correct and should
not be flagged.

**A4. Priority left implicit.** Two rules that conflict only sometimes, with no
stated tie-break. Any prompt with more than ~15 rules needs an explicit
precedence order, or the model picks one arbitrarily per call.

## B. Examples vs rules

**B1. Examples that violate stated constraints.** Models weight demonstrations
above instructions. An example 25 words long under a stated 35-word floor makes
the real floor 25. Every example must satisfy every rule, or the rule is decorative.

**B2. Examples that teach an unintended pattern.** If all five examples happen to
open the same way, that structure gets copied even though nothing asked for it.
Check diversity along every axis you care about, not just topic.

**B3. Too few or too many.** 3–5 is the useful range for format and tone. One
example is a template the model will clone near-verbatim; a dozen is mostly cost.

**B4. Verbatim leakage.** If real outputs closely echo an example's wording, the
model is copying phrases rather than learning shape. Reword the example to be
structurally identical but lexically distinct, and re-check.

## C. Structure and placement

**C1. Long content in the wrong place.** Put documents and long context at the
top, above instructions and the query. Queries at the end measurably improve
quality on long multi-document inputs.

**C2. Buried rules.** A constraint mentioned once mid-paragraph competes with
headed, formatted rules. If it matters, give it structure.

**C3. Restated rules.** A trailing checklist that repeats the body verbatim is
pure token cost and, worse, drifts out of sync with the body over time. Either the
checklist is the rule or the body is. Pick one. Deleting a duplicated checklist is
often the single largest safe token cut available.

**C4. No output contract.** Unspecified format is the most common cause of
"inconsistent output". Specify the shape, and prefer structured outputs / strict
tool schemas over asking politely for JSON.

**C5. Inconsistent delimiters.** Mixed XML, markdown, and ad-hoc separators for
the same kind of content. Pick one scheme; use consistent tag names.

## D. Underspecification

**D1. Missing edge cases.** What should the model do with empty input, conflicting
input, or a case none of the rules cover? Silence here means invention.

**D2. No abstain path.** Every prompt that can encounter incoherent input needs a
defined "flag for review" output. Without one, the model fabricates something
plausible rather than admitting the data does not support an answer.

**D3. Unstated audience or purpose.** Explaining *why* generalizes better than
listing prohibitions. "Never use ellipses" produces narrow compliance; "this is
read aloud by a TTS engine that cannot pronounce ellipses" produces the whole
family of correct behavior.

**D4. Undefined vocabulary.** Domain terms the model must classify by, with no
definition or discriminating example.

## E. Rules that cannot bind

**E1. Unmeasurable self-checks.** "Verify every ID appears exactly once", "count
the items before answering". Models are unreliable counters; this belongs in code
around the call, not in the prompt. Delete it and add the check outside.

**E2. Word-count limits.** Tokenization makes exact word counts ineffective.
Specify sentence or paragraph counts instead.

**E3. Constraint stacking.** Twenty simultaneous hard constraints plus a
thirty-item checklist do not all bind. Rank them, cut the tail, and enforce the
ones that matter in code.

**E4. Vague quality adjectives.** "High-quality", "professional", "well-structured"
give no gradient. Replace with the observable property you actually want.

## F. Stale patterns

Flag on sight (the linter catches these):

| Pattern | Status | Replacement |
|---|---|---|
| Prefilled assistant turn | Returns **400** on Claude 4.6+ | Structured outputs; or "respond directly without preamble" |
| `budget_tokens` | Rejected on Opus 4.7+ | Adaptive thinking with `effort` |
| "CRITICAL: You MUST use this tool" | Causes **over**triggering on 4.x | Plain "Use this tool when…" |
| Exact word-count limits | Never bound well | Sentence or paragraph counts |
| "Take a deep breath", tip offers, "you are a world-class…" | No measured effect on current models | Delete |
| Manual `<thinking>` scaffolding | Redundant when extended thinking is on | Remove, or keep only if thinking is off |

Also flag over-prescriptive reasoning ("follow exactly these 7 steps") on
reasoning models — general direction outperforms rigid step lists.

## G. Cost and caching

**G1. Volatile content early.** Anything that changes per request placed before
stable content invalidates the cache prefix for everything after it. Order is
tools → system → messages; put timestamps, user context, and per-request data
*after* the stable block.

**G2. Compression before correctness.** Do not shrink a prompt that does not yet
work. Once it does, cut and re-run the diff. Deleted duplication is free;
telegraphic rewording of instructions is not, and drifts behavior past ~2–3×.

**G3. Growth by accretion.** Compare the current version against the smallest
historical version, not the previous one. Prompt archives routinely show a
"compression pass" that leaves the prompt larger than it was five versions ago.

## H. Hygiene

**H1. Duplicate lines**, unbalanced tags, dead placeholder text (`[insert X]`),
leftover TODOs. Cheap to fix, and a prompt that ships `[paste example here]` is
shipping a bug.

**H2. Negation-heavy phrasing.** Long prohibition lists bind worse than positive
instruction. Convert the highest-frequency violations to "do X" form; keep
prohibitions for genuine hard limits.

**H3. No version identity.** If outputs cannot be traced back to the prompt
version and model that produced them, no comparison downstream is trustworthy.
Recommend a version stamp in the prompt and in the output metadata.
