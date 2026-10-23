# model-orchestrator

A portable [Agent Skill](https://agentskills.me/specification) that assesses a
task, decides which model tier each piece of work should run on, spawns capped
subagents accordingly, verifies the results, and synthesizes — instead of
running everything on one model.

## Why

The mechanism for per-subagent model selection already exists in modern coding
CLIs. What's missing is a *policy*: how to decide, per shard, whether it needs a
deep reasoner, the standard workhorse, or a cheap fast model — without
blanket-routing everything to the biggest (slow, costly) or the default (misses
the one hard shard). This skill is that policy, plus a cap and a verify/recover
loop.

## How it's built (two layers)

- **Part A — Policy:** harness-agnostic decision engine in abstract tiers
  (`frontier` / `deep` / `standard` / `cheap`). This is the portable 90%.
- **Part B — Bindings:** maps those tiers to real models + the spawn mechanics of
  one CLI. **Claude Code is filled in and ready. Gemini CLI and Codex/GPT are
  stubs** with a completion checklist — swap ~15 lines to port, no logic drift.

The `SKILL.md` format is an open standard loaded natively by 30+ tools, so the
same file installs everywhere; only the active binding differs.

## Use

```
/model-orchestrator [max_agents] <task>
```

- `max_agents` (optional, default 4) — hard ceiling on spawned agents.
- It prints a routing plan first, then fans out, verifies high-risk shards, and
  synthesizes. For small tasks it says "solo is faster" and just does it.

## Install (Claude Code)

Copy the folder into your skills dir:

```
cp -r model-orchestrator ~/.claude/skills/
```

Restart the session; invoke with `/model-orchestrator`.

## Routing rules (the short version)

- Score each shard by **reasoning load** (hard / standard / mechanical) and
  **risk** (auth, crypto, payments, migrations, deletes…).
- hard OR high-risk → `deep`; standard + low-risk → `standard`; mechanical →
  `cheap`.
- **Ceiling:** a worker is never more capable than the orchestrator, and
  `frontier` is orchestrator-only.
- **Verify/recover:** high-risk output gets checked; a failed or under-scored
  shard escalates one tier and re-dispatches — just that shard.

## Porting to Gemini CLI / Codex (GPT)

Open `SKILL.md` → Part B. Each stub lists the five things to confirm (current
model IDs, per-subagent model override, parallel launch, recon agent,
isolation) and where to fill the allowed-worker rows. Cross-*vendor* fan-out
(one CLI driving another) needs a bridge/MCP — a skill alone can't shell out to
another vendor.

## License

MIT (edit to taste before publishing).
