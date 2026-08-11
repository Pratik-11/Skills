# Current guidance and stale patterns

What to apply when rewriting, and what to flag as out of date. Model behavior
moves; re-check the linked docs rather than trusting this file indefinitely.

Primary source: `platform.claude.com/docs/en/build-with-claude/prompt-engineering/`
(the older per-technique pages now redirect into one consolidated best-practices
page).

## Techniques, in the order they pay off

**1. Be specific about the desired behavior.** The reliable test: show the prompt
to a colleague with no context. If they would be confused, the model will be.
Sequential numbered steps when order or completeness matters.

**2. Explain why.** Motivation generalizes; bare prohibition does not. "Never use
ellipses" → "this is read aloud by a TTS engine that cannot pronounce ellipses"
produces correct behavior on cases the rule never named.

**3. Examples.** The strongest lever for format, tone, and structure. 3–5,
relevant, and deliberately diverse so the model does not learn an accidental
pattern. Wrap them in consistent tags.

**4. Structural delimiters.** One tag per content type, consistent names, nested
for hierarchy. Any consistent scheme works; inconsistency is what costs you.

**5. Role in the system prompt.** One sentence measurably focuses tone and domain.

**6. Long-context ordering.** Long documents at the **top**, above instructions and
the query. Query last. Worth up to ~30% on complex multi-document inputs. For
extraction over long inputs, have the model pull relevant quotes first, then answer
from them.

**7. Say what to do, not what not to do.** "Do not use markdown" → "write in
flowing prose paragraphs." Also: the style of the prompt leaks into the output —
a markdown-heavy prompt produces markdown-heavy responses.

**8. Reasoning.** On thinking-enabled models, prefer general direction ("think
through the edge cases") over prescriptive step lists. Ask for an explicit
self-check against named criteria. With thinking off, note that some models are
oversensitive to the literal word "think" — "consider" or "reason through" is safer.

## Deprecated — flag on sight

| Pattern | Status | Do instead |
|---|---|---|
| Prefilled assistant turn | **400 error** on Claude 4.6+ | Structured outputs for format; "respond directly without preamble" + strip in post-processing |
| `budget_tokens` | Rejected on Opus 4.7+ | Adaptive thinking with `effort` |
| "CRITICAL: You MUST use this tool when…" | Causes **over**triggering on 4.x | "Use this tool when…" |
| Exact word-count limits | Tokenization makes these non-binding | Sentence or paragraph counts |
| "Take a deep breath" / tip offers / "world-class expert" | No measured effect on current models | Delete |
| Manual `<thinking>`/`<answer>` scaffolding | Redundant with extended thinking | Keep only if thinking is off |
| Heavy anti-laziness pressure | Now overcorrects | State the requirement once, plainly |

Anthropic's own Console prompt improver still emits prefill guidance. Treat its
output as a draft to audit, not as ground truth.

## Structured output

Prefer constrained decoding (JSON output config with a schema, or strict tool use)
over asking for JSON in prose. It removes parse-retry logic entirely.

It does **not** remove the need for prompt work — schema conformance is not content
correctness. Known gotchas: unsupported schema features (recursion, complex regex,
external refs), enum capitalization drift (compare case-insensitively), and
`max_tokens` truncation producing invalid output regardless of the schema.

## Caching, for large system prompts

Prefix order is tools → system → messages. A change at any level invalidates that
level and everything after it.

Place the cache breakpoint on the last block that is **byte-identical across
requests**. Anything volatile — timestamps, per-request user context, retrieved
documents that change — goes after the breakpoint. Cache reads cost ~0.1× base;
writes 1.25–2×. Verify with `cache_read_input_tokens` in the response.

A common own-goal: injecting the current date at the top of a long system prompt,
which invalidates the entire cache on every call.

## Cost

Engineer for quality first, compress second. Compressing before the prompt works
hides what good performance looks like and you lose the reference point.

When cutting: delete duplication, then unbindable rules, then reword. Measure after
each step.
