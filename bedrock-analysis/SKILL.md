---
name: bedrock-analysis
description: Run a full 360° Amazon Bedrock FinOps and observability analysis using the `aingel` CLI — spend breakdown across every active region, per-model unit economics, prompt-cache economics, latency/throttling health, anomaly detection, end-of-month forecast, and prioritized cost-optimization recommendations with dollar estimates. Use whenever the user asks to analyze, audit, review, or optimize Amazon Bedrock costs, token usage, model spend, or LLM inference bills on AWS; asks "why did my Bedrock bill go up"; wants a Bedrock cost report for a client or account; or mentions aingel. Also use for cross-account and multi-account Bedrock reviews via `--role-arn` or CloudKeeper Prism.
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
aingel cache warm      # one-time ~15s; without it the dashboard skips TPM headroom
```

`doctor` is the gate. Do not proceed past a failing check — every later number
depends on it. Confirm the **account id** it prints is the one you were asked to
analyze before writing anything.

| Check | If it fails |
|---|---|
| `sts:identity` | Credentials are wrong/expired. Confirm the intended account id. |
| `cost-explorer` | CE must be enabled **on the payer account**; a linked account often can't read it. Billed-dollar analysis is impossible — say so rather than substituting list price silently. |
| `cloudwatch` | The region-discovery probe failed (usually permissions), so aingel can't tell which regions run Bedrock — usage figures can't be trusted. When it passes, the detail line lists the active regions: check it matches where the client says the workload runs. |
| `bedrock` | Control-plane access missing; model catalog and inference-profile resolution degrade. |
| `invocation-logs` | Not a failure — a **finding**. See "Invocation logging" below. |

**Choosing an account.**
- **Own account:** `--profile` / `AWS_PROFILE` (or `AINGEL_PROFILE`).
- **Client account, direct:** `--role-arn <arn>` (plus `--external-id` only for
  legacy roles whose trust policy still requires one). The client deploys the
  role from aingel's CloudFormation.
- **CloudKeeper Prism:** `aingel doctor` has a `prism ▸` entry (←/→ to reach it,
  Enter to open) listing every account you can enter with a read-only role; the
  pick persists across terminals. `aingel accounts --json` is the scriptable
  equivalent.

**The read-only gate.** Before using any assumed role — Prism *or* a bare
`--role-arn` — aingel checks what the role can do and refuses (exit 1) any role
that can write. A role that is read-only but broader than aingel needs (it can
read secrets or customer data) is also refused unless `--allow-broad` is passed.
**Never add `--allow-broad` on your own** — tell the user what was refused and
let them decide; the fix is usually to have the client deploy aingel's own
narrower role. `--strict` goes the other way and accepts only an exact match.
CloudKeeper's own `cross-account-bedrock-ops-role` classifies **SENSITIVE** by
design (it can read the invocation-log S3 bucket), so for that role `--allow-broad`
is the expected, user-approved state, not a smell.

**Regions are automatic.** Cost Explorer is global; CloudWatch is regional, so
aingel discovers every region with Bedrock activity (a free `ListMetrics`
fan-out, cached 24h) and merges them into one snapshot. Only pin when you mean
it: `--regions us-east-1,eu-west-1` for a fixed set, `--region X` for exactly
one. Run `aingel regions` early — it is the per-region split (MTD spend, tokens,
latency, throttles, logging) and tells you where the workload actually lives.

`regions` lists every region that is **either** active in CloudWatch **or** billed
in Cost Explorer this month. A billed-only row shows spend and share with the
CloudWatch columns as `—` and a reason in INVOKES: `not probed` (discovery was
denied or timed out there), `no metrics` (probed, idle, yet billed — batch or
provisioned charges), `not pinned` (you pinned a set that excludes it). The
trailer reads `16 not probed · 11 quiet`; a billed-only region is never "quiet".
Expect ~10 s per CloudWatch-reading command: discovery probes ~28 regions with an
8 s cap each, so one unreachable endpoint cannot stall a command.

Watch for the yellow `⚠` block:
- **unreachable** — a region known to be active whose CloudWatch fetch failed
  this run. Its tokens are incomplete and cost falls back to list price. Say so
  in the report; don't publish its per-model figures as complete.
- **not probed — coverage unknown** — discovery was denied or timed out there.
  Numbers still reconcile, but only over the regions that answered.
- **$X billed in regions without token data, outside the rate (…) settled A→B** —
  Cost Explorer sees spend in regions whose tokens aingel could not read. That
  money is deliberately **excluded from the effective rate** (numerator and
  denominator cover the same regions) and is **not** in the reconciled cost
  column. Report it separately, from `costs --by region`, never as "unknown".
- **N inference profile(s) unresolved (…)** — an application inference profile's
  id could not be mapped to its model (the `ListInferenceProfiles` call failed or
  was denied). Its tokens are unpriced and left out, and the **rate is
  suppressed** — every cost on that screen is list price, and the headline says
  so. aingel retries on the next run; if it persists, check the role's
  `bedrock:ListInferenceProfiles` permission. Never report that spend as zero.

**Many regions "not probed" while `costs --by region` shows spend there** almost
always means an **organization SCP** restricting `aws:RequestedRegion` — the
account may invoke models anywhere (global routing) but nothing may *read*
outside the home region. That is a finding about the customer's org policy, not
about aingel. The fix that keeps the SCP's intent is an exception for just
`cloudwatch:GetMetricData` and `cloudwatch:ListMetrics` outside the home region,
scoped by `aws:PrincipalArn` to the read-only role; with it the token side fills
in and the ⚠ block disappears.

## Phase 1 — Sweep

**Always pass `--raw`.** By default aingel prints a widget band — small charts
above each table — sized for a human at a terminal. `--raw` suppresses it and
gives the plain tables, which is what you want when you are reading the output
rather than looking at it. It is also the stable contract: bands may change
shape between releases, `--raw` will not.

```bash
aingel dashboard --raw                       # start here: spend, WoW + why, health, top actions
aingel regions --raw                         # where the spend and traffic live
aingel costs --days 30 --by service --raw    # billed dollars, daily trend
aingel costs --days 30 --by model --raw      # also: region | account | usagetype | operation
aingel usage --days 14 --raw                 # invocations, tokens, cache read/write, throttles
aingel economics --days 14 --raw             # $/call, tokens/call, IN:OUT, $/1K out, cache $, latency
aingel assess --days 14 --raw                # rule-based recommendations with $/mo estimates
aingel anomalies --raw                       # robust z-score spike detection (exit code 2 if found)
aingel forecast --raw                        # end-of-month projection
aingel models --raw                          # what's available + catalog list price
```

Use `--json` instead wherever you are parsing rather than reading. When you want
to *show* a chart to the user — a spend shape, a cache-economics split — drop
`--raw` and paste the banded output verbatim; that is what the band is for.
`-x/--explain` appends a legend for every column shown.

**Windows (`--days` defaults):** `usage` 7 · `economics`, `assess`, `sync` 14 ·
`costs`, `trends` 30 · `anomalies` 60. Keep `usage`/`economics`/`assess` at
**≤ 14 days** — that is what their live CloudWatch reads are built for (the help
text says so, but nothing enforces it). For longer history, `aingel sync` once,
then `aingel trends --raw` reads the local rollup store offline.

Useful extras: `costs --top N` (default 15 groups), `models --provider <name>`,
`anomalies --threshold <z>` (default 3.0) and `--min-impact <$>` (default $1/day)
to tune sensitivity.

`forecast` prints two different numbers on purpose: **projected EOM** is the
run-rate method (settled daily average × days left, plus month to date) and **CE
forecast** is Cost Explorer's own whole-month projection with its 80% interval.
Quote both; they legitimately differ.

`aingel live` is an auto-refreshing monitor for something happening *right now*.
It prices every row at **list price**, never reconciled — don't quote its
dollars in a written analysis.

## Phase 2 — Interpretation

This is where you earn the engagement. The tool reports; you explain.

### Reconciled cost — always lead with billed dollars
aingel derives each model's **effective** price as `billed ÷ list-estimate`, so
reported cost tracks the real invoice rather than catalog price. The rate comes
from a **settled** window of the same length as `--days` but ending 3 days ago
(Cost Explorer's billing lag), then applied to the recent usage — so recent
tokens are priced at a rate that has finished billing.

- **EFF/LIST < 1** — paying under list. Discounts, an EDP/PPA, or prompt caching.
- **EFF/LIST ≈ 1** — no negotiated discount is landing. For a large spender this
  is itself a finding: worth a commercial conversation.
- **EFF/LIST > 1** — usually cache *writes* (billed above the input rate) or a
  model mix the estimator maps imperfectly. Investigate before reporting it as
  overspend. If usage shifted sharply in the last few days, the settled rate may
  lag behind it — say so.

The rate is derived **per model**: each Cost Explorer per-model service line
("Claude Sonnet 5 (Amazon Bedrock Edition)") is matched to its CloudWatch model
id by exact version — Sonnet 5 never absorbs Sonnet 4.5's dollars and a `v2`
release never absorbs `v1`'s. A service line with **no priced model** behind it is
not matched; its dollars appear in the footer as **`+$X unmatched`**. That is a
catalog gap (a model aingel has no price for), not a saving and not an error:
report the spend as billed-but-unreconciled and add the price to
`~/.aingel/pricing.json`. The generic "Amazon Bedrock" line (Nova, Titan,
Knowledge Bases, Guardrails) is never counted there.

Catalog prices are **US / global inference-profile on-demand rates**. Regional
`eu.` / `apac.` profiles bill ~10% higher on Bedrock; the effective rate absorbs
that when Cost Explorer is available, the list-price fallback does not — say so
for an EU/APAC-heavy account priced at list.

If Cost Explorer is unavailable, everything falls back to list price — label it
"list-price estimate" everywhere and never present it as billed spend.

**Month-to-date vs run rate** are different numbers on purpose: MTD is Cost
Explorer's true total including today's partial day; the daily run rate averages
only *settled* days. Early in a month the rate and projection show `—` — report
that, don't fill it in.

**The dashboard's `why:` line** splits the week-over-week cost change into
volume, model mix and effective rate, as percentages of prior-week spend that
sum to the headline. A model that did not exist last week lands in **mix** at
its current rate (the mix got more expensive), not in rate; a rate change is
the same traffic billed differently. Quote the split — it is the one-line
answer to "why did the bill move".

### What `assess` actually computes
Know the rules so you can defend or adjust each estimate. Every rule runs on
reconciled cost, scaled to a month as `30 ÷ window days`:

| Rule | Fires when | $/mo estimate (assumption) |
|---|---|---|
| right-size | premium model with a cheaper alternative, ≥ $10/mo | (cost − alt cost) × 0.5 — half the traffic moves. Severity HIGH if the model is > 50% of spend |
| legacy-model | superseded generation, ≥ $1/mo | cost − successor cost, if positive |
| prompt-caching | input:output ≥ 4, ≥ $5/mo, cache hit < 50% | uncached input cost × 0.6 × 0.9 — 60% cacheable, 90% saved |
| batch | ≥ 100k calls/mo and ≥ $50/mo | cost × 0.3 × 0.5 — 30% batchable at half price |
| output-heavy | output:input ≥ 2, ≥ $5/mo | none (informational) |
| throttling | throttle rate ≥ 1% (HIGH at ≥ 5%) | none |
| server-errors | server errors ≥ 2% of calls | none |
| unpriced-model / no-usage | model missing from the catalog / nothing found | none — data gap, check the region list |

When several rules hit the same model, their savings are scaled down so the
total never exceeds that model's own spend — the headline is not a simple sum.
The assumptions (50%, 60%, 30%) are deliberately conservative defaults; once the
user tells you what a workload is, replace them with real figures and say you
did.

### Prompt caching economics (the most common real win)
For Claude models with the default 5-minute cache: read ≈ **0.10×** the input
rate, write ≈ **1.25×**. Each read token saves `0.90×`, each written token costs
`0.25×` extra — caching turns a profit once **read ÷ write > 0.28**, roughly one
reuse per write. aingel's `REUSE` and `NET` columns use exactly these rates.

The rates are **model-specific**: the 1-hour cache option bills writes higher
(2× on Anthropic's own API — confirm on the Bedrock pricing page), some newer
models have lower read rates, and Amazon Nova caches implicitly. For anything
other than a 5-minute Claude cache, recompute the break-even from the pricing
page before recommending.

- High `IN:OUT` ratio + repeated system prompts/RAG context → strong candidate.
- `REUSE` below ~0.28 → caching is **losing** money: writes are never read back,
  usually because traffic is too sparse for the cache TTL or the prefix changes
  every call. Negative `NET` confirms it; recommend fixing the prefix or raising
  request density, not "enable caching".
- `REUSE` between 0.28 and ~2 → working but thin; there is headroom.
- High `CACHE HIT` with clearly positive `NET` → working; quantify it and move on.
- Batch inference does **not** support prompt caching — don't stack the two
  savings on the same traffic.

### Model mix and concentration
- If one model dominates spend (a good rule of thumb: > 70%), that is the lever
  — everything else is noise. (This is an analyst heuristic; aingel's own bump
  is at 50%, and the economics table labels concentration by a Herfindahl index.)
- Premium model on high-volume, low-complexity traffic → propose routing a share
  to a cheaper model. Be concrete: "route the ~40% of calls under 500 output
  tokens to Haiku" beats "consider a cheaper model".
- Old generation with a current successor → usually cheaper *and* better; check
  `aingel models` for availability in that region.

### Output-heavy workloads
Low `IN:OUT` with high `$/1K OUT` → audit `max_tokens` and verbosity. Output
tokens cost several times input; runaway generation is a silent tax.

### Reliability and throttling
- `THROTTLED` > 0 is a capacity signal. Remedies, roughly in order: cross-region
  inference profiles (geographic, or global where data residency allows) →
  quota increase → the **Priority** or **Reserved** service tier → provisioned
  throughput (only at sustained volume; inference profiles don't support it).
- `TPM headroom` on the dashboard under ~20% means throttling is imminent. If
  the line is missing, `cache warm` hasn't been run.
- Elevated server errors = wasted retry spend; retried long generations still
  bill input tokens. Quantify it.

### Latency
p50/p90/p99 plus TTFT p90. A p99 far above p50 means a slow tail — usually long
outputs or a saturated model. Tie it to the model, not the account.

### Anomalies
Robust z-score (median/MAD) against a 14-day baseline, so a single spike doesn't
hide itself; each finding carries its region. Every anomaly needs a cause before
it goes in a report — cross-check the date against `costs --by model` and
`usage` to name what changed.

### Invocation logging (capability discovery)
`doctor`'s `invocation-logs` line and the dashboard's `invocation logging` line
report whether Bedrock model-invocation logging is on and **whether an S3
destination exists**. Request/response bodies over **100 KB** are not stored
inline in CloudWatch Logs — they go to the S3 large-data-delivery location. So:

- **off** → no prompt/response data exists. Recommend enabling it (cheap, and it
  unlocks prompt-level optimization). It only captures traffic from the moment
  it's switched on.
- **on, CloudWatch only** → the **largest prompts and responses are missing** —
  exactly the ones worth optimizing. Recommend adding an S3 destination.
- **on with S3** → full fidelity. Name the bucket(s) and flag that prompt-level
  analysis (caching candidates, redundant context, oversized system prompts) is
  possible.

Logging is per region — `aingel regions` shows it per row. Treat it as a
prerequisite finding: it gates what a follow-up engagement can do.

## Phase 3 — Go beyond the rules

`aingel assess` applies deterministic rules. The findings customers remember
usually come from combining signals it doesn't cross — this is your job:

- Correlate an anomaly date with a deploy, a launch, or a batch job.
- Compare `costs --by usagetype` against `usage` to catch billing surprises the
  token math alone won't show.
- Look for models with meaningful spend but tiny call counts (an experiment left
  running) or huge call counts at trivial cost (a health-check loop).
- Compare regions: the same model at very different latency or throttle rates
  across regions is a routing finding.
- Ask the user what the workloads *are*. "Which of these is user-facing?" turns a
  table of model ids into an actionable recommendation, and the answer is not in
  any API.

**Levers `assess` doesn't model** — check each against the workload before
recommending, and price it from the current Bedrock pricing page (discounts vary
by model and change):

| Lever | Fits | Note |
|---|---|---|
| Batch inference | async work: evals, backfills, bulk enrichment | 50% of on-demand for supported models; no prompt caching |
| Flex service tier | latency-tolerant, non-interactive | discounted; check the per-model rate |
| Global cross-region inference | no data-residency constraint | priced below geographic profiles; also eases throttling |
| Reserved service tier | steady, high, predictable TPM | 1- or 3-month commitment; minimums apply |
| Intelligent prompt routing | mixed-difficulty traffic within one model family | routes each request to the cheaper model that meets the bar |
| Model distillation | one narrow, high-volume task | a trained smaller model; an engagement, not a switch |

When you need data aingel doesn't expose, you have AWS credentials — query Cost
Explorer or CloudWatch directly. Stay read-only.

## Phase 4 — Deliverable

Default to a written summary in this shape:

1. **Headline** — spend over the window, trend vs prior period, projected
   end-of-month, and whether figures are billed or list-price estimates.
2. **Where the money goes** — concentration by model (and by region if more than
   one), with shares.
3. **Health** — goodput, throttling, latency tail, quota headroom.
4. **Findings** — ranked by dollar impact. Each: what, evidence (the number and
   the command it came from), recommended action, estimated $/mo, and confidence.
5. **Caveats** — account id, region coverage (the `regions` trailer: how many
   not probed, how many quiet; any unreachable region), spend outside the rate
   (the `$X billed in regions without token data` line, with its settled
   window), unresolved inference profiles, unmatched spend, CE availability,
   window length, and whether invocation logging limits deeper analysis.

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

Every command supports `--json`; multi-region output adds `regions`,
`partial_regions`, `unprobed_regions` and `by_region` keys, and the usage-style
snapshots carry `unresolved_profiles`. `usage`, `economics` and `assess` include a
`reconciliation` object: `overall_factor`, per-model `factors`, `unmatched_usd`,
`out_of_scope_usd` (region → dollars outside the rate), `out_of_scope_total_usd`,
and the settled window as `window_start` / `window_end` (**end exclusive**; the
screen prints it inclusive). `assess --json` is `[]` when nothing fires.
`regions --json` adds `quiet`. `--no-cache` forces
fresh data (responses are cached on disk, so repeat runs are near-instant;
`doctor` always runs live). `aingel cache` shows cache stats, `cache clear`
purges it.

## Failure modes to avoid

- **Reporting list price as billed spend** — including anything from `live`.
  Check the reconciliation note under each table.
- **Ignoring a `⚠` region line.** An unreachable region means incomplete tokens
  and list-price fallback; say so.
- **Treating a "not probed" region as having no spend.** `regions` and
  `costs --by region` show the billed dollars; the token side is what is missing.
- **Quoting `+$X unmatched` as a saving or an error.** It is billed spend with no
  catalog price; report it and fix the catalog.
- **Treating an unresolved inference profile as zero spend.** The headline
  says it is left out and that costs are list price; the tokens are real.
- **Pinning `--region` out of habit.** It hides every other region; let
  discovery run unless you mean to narrow.
- **Recommending prompt caching without checking REUSE/NET** — or using the
  5-minute Claude rates for a different model or TTL.
- **Stacking batch and caching savings on the same traffic.** Batch doesn't
  support caching.
- **Recommending provisioned throughput or Reserved on spiky traffic.** They only
  pay at sustained, predictable volume.
- **Quoting an anomaly without a cause.** Find what changed, or label it
  explicitly as unexplained.
- **Passing `--allow-broad` without the user's say-so.**
- **Analyzing the wrong account.** Confirm the account id from `doctor` before
  writing anything.
