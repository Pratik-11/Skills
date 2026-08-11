# Skills

Claude Code skills. Copy a skill's folder into `~/.claude/skills/` to use it.

## bedrock-analysis

A 360° Amazon Bedrock FinOps and observability review: spend breakdown, per-model
unit economics, prompt-cache economics, latency and throttling health, anomaly
detection, end-of-month forecast, and prioritized cost recommendations with dollar
estimates.

Requires the `aingel` CLI, which does the data collection and math. `aingel` is not
yet published — install and usage instructions will ship with it.

## prompt-optimizer

Audits and optimizes LLM prompts with measured evidence, and never claims an
improvement it did not measure. Finds contradictory rules, examples that violate
the prompt's own constraints, and stale API patterns; builds an eval set from real
failures; rewrites; then proves the new version is better with a before/after diff.

Includes `scripts/lint.py` and `scripts/check.py`, run via `python3`.

## License

MIT — see [LICENSE](LICENSE).
