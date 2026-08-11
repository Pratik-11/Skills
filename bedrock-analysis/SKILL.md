---
name: bedrock-analysis
description: Run a full 360° Amazon Bedrock FinOps and observability analysis using the `aingel` CLI — spend breakdown, per-model unit economics, prompt-cache economics, latency/throttling health, anomaly detection, end-of-month forecast, and prioritized cost-optimization recommendations with dollar estimates. Use whenever the user asks to analyze, audit, review, or optimize Amazon Bedrock costs, token usage, model spend, or LLM inference bills on AWS; asks "why did my Bedrock bill go up"; wants a Bedrock cost report for a client or account; or mentions aingel. Also use for multi-account Bedrock reviews via CloudKeeper Prism.
---

# Bedrock Analysis

A repeatable method for turning an AWS account into a defensible Bedrock cost
analysis. `aingel` does the data collection and math (~90% of the work); your job
is the 10% that needs judgment — reading the numbers in context, spotting what
the rules miss, and writing findings the customer can act on.

**`aingel` is strictly read-only.** It calls Cost Explorer, CloudWatch, the
Bedrock control plane, Service Quotas and STS. It never invokes a model, never
writes, and never spends money.

## Phase 0 — Setup (do this first, every time)

```bash
aingel version || go install github.com/cloudkeeper/aingel@latest
aingel doctor          # verify credentials + every API aingel needs
```

`doctor` is the gate. Do not proceed past a failing check — every later number
depends on it. Read its output carefully:

| Check | If it fails |
|---|---|
| `sts:identity` | Credentials are wrong/expired. Confirm the intended account id. |
| `cost-explorer` | CE must be enabled **on the payer account**; a linked account often can't read it. Billed-dollar analysis is impossible — say so rather than substituting list price silently. |
| `cloudwatch` | "no AWS/Bedrock metrics in this region" usually means the workload is in **another region**, not that there's no usage. Re-run with `--region`. |
| `bedrock` | Control-plane access missing; model catalog and inference-profile resolution degrade. |
| `invocation-logs` | Not a failure — a **finding**. See "Invocation logging" below. |

**Choosing an account.** For a single account, use `--profile`/`--region` or
`AWS_PROFILE`. For CloudKeeper Prism users, `aingel doctor` has a `prism ▸` entry
(←/→ to reach it, Enter to open) listing every account you can enter with a
read-only role; picking one persists across terminals. `aingel accounts --json`
is the scriptable equivalent. aingel refuses any Prism account whose role is not
verifiably read-only.

**Region matters.** CloudWatch metrics are per-region; Cost Explorer is org-wide.
If billed cost is non-zero but usage is empty, you are looking at the wrong
region — find the right one before concluding anything.

## Phase 1 — Sweep

Run these and keep the output. Add `--json` when you want to compute on it;
prefer the human tables when you are going to quote them in a report. Every
command takes `--days N` (default 7–30 depending on command) and `-x/--explain`
to print a column legend.

```bash
aingel dashboard                 # start here: spend, WoW + why, health, top actions
aingel costs --days 30 --by service     # billed dollars, daily trend
aingel costs --days 30 --by model       # also: region | account | usagetype | operation
aingel usage --days 14                  # invocations, tokens, cache read/write, throttles
aingel economics --days 14              # $/call, tokens/call, IN:OUT, $/1K out, cache $, latency
aingel assess --days 14                 # rule-based recommendations with $/mo estimates
aingel anomalies --days 45              # robust z-score spike detection (exit code 2 if found)
aingel forecast                         # end-of-month projection
aingel models                           # what's available + catalog list price
```

For history beyond CloudWatch's ~2-week retention: `aingel sync` once, then
`aingel trends` reads the local rollup store offline.

`aingel live` is an auto-refreshing monitor — use it when investigating something
happening right now, not for a written analysis.

## Phase 2 — Interpretation

This is where you earn the engagement. The tool reports; you explain.

### Reconciled cost — always lead with billed dollars
aingel derives each model's **effective** price as `billed ÷ list-estimate` over
the window, so reported cost tracks the real invoice rather than catalog price.

- **EFF/LIST < 1** — paying under list. Discounts, an EDP/PPA, or prompt caching.
- **EFF/LIST ≈ 1** — no negotiated discount is landing. For a large spender this
  is itself a finding: worth a commercial conversation.
- **EFF/LIST > 1** — usually cache *writes* (billed ~1.25× input) or a model mix
  the estimator maps imperfectly. Investigate before reporting it as overspend.

If Cost Explorer is unavailable, everything falls back to list price — label it
"list-price estimate" everywhere and never present it as billed spend.

### Prompt caching economics (the most common real win)
Billing: cache **read ≈ 0.10×** the input rate, cache **write ≈ 1.25×**. So each
read token saves `0.90×` and each written token costs `0.25×` extra — caching
turns a profit once **read ÷ write > 0.28**, i.e. roughly *one reuse per write*.

- High `IN:OUT` ratio (input-heavy) + repeated system prompts/RAG context →
  strong caching candidate.
- `REUSE` (read ÷ write) below ~0.28 → caching is **losing** money: writes are
  never being read back, usually because traffic is too sparse for the ~5-minute
  cache TTL or the prefix changes every call. `NET` (saved − write cost) going
  negative confirms it; recommend fixing the prefix or raising request density,
  not "enable caching".
- `REUSE` between 0.28 and ~2 → working but thin; there is headroom.
- Already-high `CACHE HIT` with clearly positive `NET` → working; quantify it and
  move on.

### Model mix and concentration
- If one model is >70% of spend, that is the lever — everything else is noise.
- Premium model on high-volume, low-complexity traffic → propose routing a share
  to a cheaper model. Be concrete: "route the ~40% of calls under 500 output
  tokens to Haiku" beats "consider a cheaper model".
- Old generation with a current successor → usually cheaper *and* better; check
  `aingel models` for availability in that region.

### Output-heavy workloads
Low `IN:OUT` with high `$/1K OUT` → audit `max_tokens` and verbosity. Output
tokens cost several times input; runaway generation is a silent tax.

### Reliability and throttling
- `THROTTLED` > 0 is a capacity signal. Fixes, in order: cross-region inference
  profiles → quota increase → provisioned throughput (only at sustained volume).
- Check `TPM headroom` on the dashboard: under ~20% means throttling is imminent.
- Elevated server errors = wasted retry spend; quantify it.

### Latency
p50/p90/p99 plus TTFT p90. A p99 far above p50 means a slow tail — usually long
outputs or a saturated model. Tie it to the model, not the account.

### Anomalies
Robust z-score against a median baseline, so a single spike doesn't hide itself.
Every anomaly needs a cause before it goes in a report — cross-check the date
against `costs --by model` and `usage` to name what changed.

### Invocation logging (capability discovery)
`doctor`'s `invocation-logs` line and the dashboard's `invocation logging` line
report whether Bedrock model-invocation logging is on and **whether an S3
destination exists**. This matters: payloads over **100 KB are not stored inline
in CloudWatch Logs** — they go to the S3 "large data delivery" bucket. So:

- **off** → no prompt/response data exists. Recommend enabling it (cheap, and it
  unlocks prompt-level optimization). Note it only captures traffic from the
  moment it's switched on.
- **on, CloudWatch only** → you have small payloads but the **largest prompts and
  responses are missing** — exactly the ones worth optimizing. Recommend adding
  an S3 destination.
- **on with S3** → full fidelity. Name the bucket(s) and flag that deeper
  prompt-level analysis (caching candidates, redundant context, oversized system
  prompts) is possible.

Treat this as a prerequisite finding: it gates what a follow-up engagement can do.

## Phase 3 — Go beyond the rules

`aingel assess` applies deterministic rules. The findings customers remember
usually come from combining signals it doesn't cross — this is your job:

- Correlate an anomaly date with a deploy, a launch, or a batch job.
- Compare `costs --by usagetype` against `usage` to catch billing surprises the
  token math alone won't show.
- Look for models with meaningful spend but tiny call counts (an experiment left
  running) or huge call counts at trivial cost (a health-check loop).
- Check whether workloads are batchable — **batch inference is 50% of
  on-demand**. Anything asynchronous (evals, backfills, bulk enrichment,
  summarization pipelines) is a candidate; interactive traffic is not.
- Ask the user what the workloads *are*. "Which of these is user-facing?" turns a
  table of model ids into an actionable recommendation, and the answer is not in
  any API.

When you need data aingel doesn't expose, you have AWS credentials — query Cost
Explorer or CloudWatch directly. Stay read-only.

## Phase 4 — Deliverable

Default to a written summary in this shape:

1. **Headline** — spend over the window, trend vs prior period, projected
   end-of-month, and whether figures are billed or list-price estimates.
2. **Where the money goes** — concentration by model, with shares.
3. **Health** — goodput, throttling, latency tail, quota headroom.
4. **Findings** — ranked by dollar impact. Each: what, evidence (the number and
   where it came from), recommended action, estimated $/mo, and confidence.
5. **Caveats** — region scope, CE availability, window length, whether invocation
   logging limits deeper analysis.

Rules for numbers: state the window with every figure; never mix billed and
list-price without labeling; round money to cents and rates sensibly; and if a
recommendation's saving is a guess, say so. Savings estimates from `assess` are
deliberately conservative — keep them that way.

For a formal client-facing document, hand off to the `enterprise-sop` skill if it
is available; otherwise a clean Markdown report is the deliverable.

## Automation

`anomalies` exits **2** when it finds spikes, so it drops into cron/CI:

```bash
aingel anomalies --json || ./notify.sh
```

Every command supports `--json`. `--no-cache` forces fresh data (responses are
cached on disk, so repeat runs are near-instant; `doctor` always runs live).

## Failure modes to avoid

- **Reporting list price as billed spend.** Check the reconciliation note under
  each table.
- **Concluding "no usage" from an empty CloudWatch result.** Check other regions.
- **Recommending prompt caching without checking REUSE/NET.** It can lose money.
- **Recommending provisioned throughput on spiky traffic.** It only pays at
  sustained, predictable volume.
- **Quoting an anomaly without a cause.** Find what changed, or label it
  explicitly as unexplained.
- **Analyzing the wrong account.** Confirm the account id from `doctor` before
  writing anything.
