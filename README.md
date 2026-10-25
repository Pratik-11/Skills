# Skills

Claude Code skills. Install one by copying or symlinking its folder into
`~/.claude/skills/` (every project) or `.claude/skills/` (one project):

```bash
git clone https://github.com/Pratik-11/Skills.git
ln -sfn "$PWD/Skills/bedrock-analysis" ~/.claude/skills/bedrock-analysis
```

| Skill | What it does | Needs |
|---|---|---|
| [`bedrock-analysis`](bedrock-analysis/SKILL.md) | A 360° Amazon Bedrock FinOps review driven through the `aingel` CLI | `aingel` on PATH, AWS credentials |
| [`prompt-optimizer`](prompt-optimizer/SKILL.md) | Audits and rewrites LLM prompts with measured before/after evidence | `python3` |
| [`morch`](morch/SKILL.md) | Routes a task across the models your CLI can spawn, by tier | a CLI with subagents (Claude Code filled in) |

## bedrock-analysis

A 360° Amazon Bedrock FinOps and observability review: spend by model and by
region, per-model unit economics reconciled to the Cost Explorer bill,
prompt-cache economics, latency and throttling health, anomaly detection,
end-of-month forecast, and prioritized cost recommendations with dollar
estimates. The skill carries the judgment the tool's rules cannot: cache
break-even, what each ⚠ coverage line means for a report, which spend is
outside the reconciled rate, batch and routing candidates, throttling remedies,
and the failure modes to avoid when writing up a client account.

It drives the [`aingel`](https://github.com/Pratik-11/aingel) CLI, a read-only
single binary that does the data collection and math. Install `aingel` first,
run `aingel doctor`, then ask Claude to "analyze my Bedrock spend" or invoke
`/bedrock-analysis`. Works on your own account, cross-account through a
read-only role (`--role-arn`), and through CloudKeeper Prism. The copy in the
aingel repository (`skills/bedrock-analysis/`) is kept identical to this one.

## prompt-optimizer

Audits and optimizes LLM prompts with measured evidence, and never claims an
improvement it did not measure. Finds contradictory rules, examples that violate
the prompt's own constraints, and stale API patterns; builds an eval set from real
failures; rewrites; then proves the new version is better with a before/after diff.

Includes `scripts/lint.py` and `scripts/check.py`, run via `python3`.

## morch

morch (model orchestrator) finds out which models your CLI can spawn right now,
ranks them into tiers, then assesses a task, decides which model each piece of
work should run on, spawns capped subagents accordingly, verifies the results,
and synthesizes — instead of running everything on one model. No model names
are hardcoded, so new releases are picked up without editing the skill.

Built in two layers: a harness-agnostic policy in abstract tiers (`frontier` /
`deep` / `standard` / `cheap`), and a bindings block that says where each CLI
lists its models and how to spawn workers. Claude Code is filled in; Gemini CLI
and Codex/GPT are stubs with a completion checklist. See its
[README](morch/README.md).

## License

MIT — see [LICENSE](LICENSE).
