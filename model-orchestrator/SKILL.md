---
name: model-orchestrator
description: |
  Assess a task, then decide the orchestration: which model orchestrates, how
  the work is decomposed into subagents, and which model tier each subagent runs
  on — capped at a max agent count, with verification and failure-recovery on the
  results. Portable across coding CLIs: a harness-agnostic Policy plus a swappable
  Bindings block (Claude Code filled in; Gemini CLI and Codex/GPT stubbed).
  Use when the user wants to fan out work across models, says "orchestrate",
  "route this", "spawn agents", "use subagents", "model-orchestrator", or passes
  a max-agents number like "/model-orchestrator 4 <task>". Also use for any large
  or parallelizable task where mixing model tiers (cheap workers, deep reasoners)
  would be faster or cheaper than doing it solo on one model.
allowed-tools:
  - Agent
  - Read
  - Grep
  - Glob
  - Bash
  - TodoWrite
---

# Model Orchestrator

Assess a task, decide *how* to run it across models, run it, verify it, and
synthesize. You are the orchestrator. The loop is **assess → route → launch →
verify/recover → synthesize** — not a straight line; a failed or under-scored
shard loops back to re-route.

## How to use this skill

It has two layers so it ports across CLIs without rewriting the logic:

- **Part A — Policy** is the decision engine. It is harness-agnostic and speaks
  in *abstract tiers* (`frontier` / `deep` / `standard` / `cheap`), never in
  concrete model names.
- **Part B — Bindings** maps those abstract tiers to real models and to the
  spawn mechanics of one specific CLI. **Claude Code is filled in; Gemini CLI and
  Codex/GPT are stubs** you complete before porting.

**First thing to do:** identify the CLI you're running in, jump to its Bindings
block, load the tier→model map + spawn mechanics, then execute Part A using them.
If a binding for the current harness is missing or still a stub, say so and fall
back to `frontier`-only solo work rather than guessing at tool names.

---

# Part A — Policy (harness-agnostic)

**Abstract capability tiers, high → low:**

| Tier       | Role                                                                     |
|------------|--------------------------------------------------------------------------|
| `frontier` | Best planner/synthesizer. **Orchestrator-only — never a worker.**        |
| `deep`     | Heavy reasoning: hard or high-risk shards.                               |
| `standard` | The default worker: scoped, well-specified work.                        |
| `cheap`    | Mechanical/bulk: renames, boilerplate, lookups. Fastest + lowest cost.  |

## What you can and can't control

- **Orchestrator = the current session model.** A skill cannot re-launch the
  main loop under a different model. You (the running model) orchestrate. If a
  different orchestrator is wanted, the user switches it in their CLI (see the
  binding). Prefer a `frontier` or `deep` model as orchestrator.
- **Worker model + agent count ARE controllable** — through the spawn mechanics
  in Part B.

## Step 1 — Parse the invocation

Args may lead with a max-agent count: `/model-orchestrator 4 refactor auth`.
- First whitespace-delimited integer → `max_agents`.
- Remainder → the task. If no task text, use the current pending task.
- No integer given → `max_agents = 4` (default).

## Step 2 — Assess before spawning (evidence, not vibes)

Route on what the task *actually* is, from evidence — not a reflex. Two failure
modes this skill exists to prevent:
- **Blanket-`deep`** — every shard on the reasoner "to be safe": slow, wasteful.
- **Blanket-`standard`** — everything on the default, then the one hard/risky
  shard fails quietly and you don't notice until it's merged.

Each shard earns its tier on its *own* signals.

**2a — Scout first (cheap, and it's your job — don't spawn for it).**
Gather real evidence with whatever tools exist:
- Size the change (how many files / call-sites) and find the blast radius (who
  imports or depends on what you're touching).
- Read the target signatures, the failing test, or the spec to gauge how
  *specified* vs. *ambiguous* the work is.
- Grep the touched paths for risk markers: `auth`, `token`, `password`,
  `crypto`, `payment`, `DELETE`/`DROP`, `migration`, money, PII.
- Check docs/web if the task leans on an API or library you're unsure of —
  confirm before routing a worker to guess at it.
Do the scouting yourself; only delegate recon to a read-only agent if the recon
itself is genuinely large.

**2b — Restate & split.** One-line restatement, then list the distinct
sub-parts. Classify shape: **Solo** (one thread / shared context) vs
**Parallel** (independent shards that don't need to watch each other).

**2c — Score each shard** on two axes, using the evidence from 2a:

| What the evidence shows | Reasoning load | Risk |
|---|---|---|
| Ambiguous spec, unknown-cause bug, algorithm/architecture design | hard | — |
| Fully specified, one clear correct way | standard | — |
| Rename / boilerplate / format / mechanical lookup | mechanical | — |
| Touches auth / crypto / payments / migrations / public API / deletes | — | high |
| Isolated, easily reverted, well-tested | — | low |

Map the scores to a tier:
- **hard OR high-risk → `deep`**
- **standard + low-risk → `standard`**
- **mechanical + low-risk → `cheap`**
- large-but-mechanical → `cheap`, split by volume; large-and-hard → split into
  smaller shards first, don't just throw `deep` at a blob.

A mixed plan is the goal — e.g. one `deep` for the risky shard, two `standard`
for the scoped edits, one `cheap` for the rename sweep — not one tier for
everything.

**Do NOT fan out when** the task is small, shards share heavy context, or
coordination + synthesis cost > the work itself. Spawning agents to edit one
file is slower than doing it. Say "solo is faster here" and do it yourself.

## Step 3 — Ceiling rule (clamp every choice)

A worker's tier must never sit above the orchestrator's — the orchestrator has
to judge and reconcile every worker's output, and a worker smarter than its
judge is wasted. Two rules:

1. **worker tier ≤ orchestrator tier.**
2. **`frontier` is orchestrator-only** — never spawn a `frontier` worker, even
   when the orchestrator is `frontier`. A `frontier` orchestrator spawns
   strictly below itself.

The concrete allowed-worker rows (which real models this permits) live in the
active binding. Pick worker tiers only from that row.

**Escalation exception:** if the orchestrator hits one shard it genuinely cannot
crack, it may spawn a *single* consultant at or above its own tier and take that
answer largely on trust (asking for help, not fanning out). Keep it rare and say
you're doing it.

## Step 4 — Cap and launch

- **The cap is a ceiling, not a target.** Use the *fewest* agents that cover the
  work. Merge shards that are individually tiny; don't spawn one agent per
  trivial file. An agent must be worth its spawn + synthesis overhead.
- Decompose into **at most `max_agents`** shards. If the natural plan needs more,
  batch several shards into one agent's prompt or drop the lowest-value shards —
  and say which you dropped. Never silently exceed the cap.
- Launch all independent agents **at once** (in parallel, per the binding's spawn
  mechanism), each with its tier's model, a role/type, and a focused prompt that
  says exactly what to return.
- **Ask each worker for a compact result** — what changed, a done/blocked
  status, and anything the orchestrator must reconcile — not a raw dump. Keeps
  synthesis context bounded so a big fan-out doesn't blow up your context.
- Read-only recon → the binding's read-only agent type. Editing shards that
  touch the same files must run sequentially or in the binding's isolation mode.

## Step 5 — Verify & recover (don't blind-trust workers)

- **Check before you trust.** For any **high-risk** shard, verify the worker's
  output before accepting it — re-read the changed file/diff yourself, or spawn
  one `cheap`/`standard` checker. Low-risk shards can be taken at face value.
- **Failure policy**, per shard:
  - Worker was **skipped or died / returned nothing** → **retry once**; still
    nothing → do it yourself or report the gap. Never silently drop it.
  - Output is **wrong/weak**, or the shard proved harder than you scored →
    **escalate one tier** (within the ceiling) and re-dispatch *just that shard*.
    That is the loop: re-score with what you now know, don't re-run the whole
    fan-out.
  - **Repeated failure**, or the shard needs context only you hold → **abort the
    delegation** and handle it in the orchestrator yourself.
- Escalate the *shard*, not the batch — one hard shard going `standard → deep`
  shouldn't re-run the others.

## Step 6 — Synthesize

Collect the (verified) worker results and produce the final answer yourself —
the orchestrator holds the shared context. Resolve conflicts between agents;
don't just concatenate their outputs. State what each agent did, what you
verified, and anything you escalated or handled yourself.

## Report the plan before running

Print a 3–5 line plan first so the choice is visible (use the binding's real
model names), e.g.:

```
Task: migrate 12 endpoints to the new client
Shape: parallel, 12 shards → capped to 4 agents (3 endpoints each)
Routing: 3× standard (mechanical migration) + 1× deep (the auth endpoint, risky)
Verify: re-read the auth diff (high-risk); trust the rest
Orchestrator: frontier (this session) — synthesizes + reconciles
```

Then launch. If the assessment says solo, skip the fan-out and just do it.

---

# Part B — Bindings

Use the block for the CLI you're running in. Each binding must define five
things: the **tier→model map**, how to **spawn a worker + set its model**, how to
**detect the orchestrator**, the **read-only recon** agent, and the
**parallel-edit isolation** mechanism — plus the concrete **allowed-worker rows**.

## Binding: Claude Code — FILLED ✅

**Tier → model:**

| Abstract   | Model    |
|------------|----------|
| `frontier` | `fable`  |
| `deep`     | `opus`   |
| `standard` | `sonnet` |
| `cheap`    | `haiku`  |

**Spawn + set model:** the `Agent` tool. Pass `model: opus|sonnet|haiku|fable`,
`subagent_type` (`general-purpose` default), and a focused `prompt`. Launch
independent agents in a single message to run them in parallel.

**Detect orchestrator:** it is the current session model (shown in the CLI). A
skill cannot change it; the user switches with `/model`.

**Read-only recon:** `subagent_type: Explore`.

**Parallel-edit isolation:** `isolation: worktree` on the `Agent` call, or run
same-file editors sequentially.

**Allowed-worker rows (ceiling applied):**

| Orchestrator (session) | Allowed worker models              |
|------------------------|------------------------------------|
| `fable`                | opus, sonnet, haiku (never fable)  |
| `opus`                 | opus, sonnet, haiku                |
| `sonnet`               | sonnet, haiku                      |
| `haiku`                | haiku only                         |

**Worked example (Fable orchestrator):** one `opus` agent for the risky auth
endpoint, three `sonnet` agents for the mechanical endpoint migrations, verify
the auth diff yourself, synthesize.

## Binding: Gemini CLI — STUB ⚠️ (confirm before shipping)

**Tier → model (placeholder — verify current model IDs):**

| Abstract   | Likely model (CONFIRM)      |
|------------|-----------------------------|
| `frontier` | *(none distinct — use `deep` as orchestrator)* |
| `deep`     | `gemini-2.5-pro`            |
| `standard` | `gemini-2.5-flash`          |
| `cheap`    | `gemini-2.5-flash-lite`     |

**Spawn + set model:** Gemini CLI has subagents; you direct one with
`@<subagent-name>` at the start of a prompt. Subagents are defined as files (in
the Gemini agents dir) with a model field. **CONFIRM:** whether a per-subagent
`model` override is settable and how to launch several in parallel.

**Detect orchestrator:** the model selected for the Gemini CLI session.

**Read-only recon:** the built-in investigator subagent (e.g.
`codebase_investigator`). CONFIRM the exact name.

**Parallel-edit isolation:** CONFIRM Gemini CLI's mechanism (worktree/branch or
sequential).

**To finish this binding:** ① confirm current model IDs + tiers, ② confirm
per-subagent model override, ③ confirm parallel launch, ④ confirm recon agent
name, ⑤ fill the allowed-worker rows using the same ceiling rule (frontier
orchestrator-only; worker ≤ orchestrator).

## Binding: Codex CLI (GPT) — STUB ⚠️ (confirm before shipping)

**Tier → model (placeholder — verify current model IDs):**

| Abstract   | Likely model (CONFIRM)              |
|------------|-------------------------------------|
| `frontier` | top reasoning model, high effort    |
| `deep`     | top reasoning model, standard effort|
| `standard` | mid / `mini` tier                   |
| `cheap`    | smallest / `nano` tier              |

**Spawn + set model:** Codex CLI supports subagents via `AGENTS.md` /
delegation, inspected and switched with `/agent`. It can spawn Codex, Claude
Code, or Gemini subagents. **CONFIRM:** how a subagent's model + reasoning
effort are pinned, and how to fan out in parallel.

**Detect orchestrator:** the model/effort chosen for the Codex session.

**Read-only recon:** a read-only subagent persona defined in `AGENTS.md`.

**Parallel-edit isolation:** CONFIRM (worktree or sequential).

**To finish this binding:** ① confirm current model IDs + reasoning-effort tiers,
② confirm per-subagent model/effort pinning, ③ confirm parallel launch,
④ define a recon persona, ⑤ fill the allowed-worker rows using the ceiling rule.

> Cross-vendor note: spawning a *different vendor's* CLI as a worker (Codex
> orchestrating a Gemini shard, etc.) needs a bridge/MCP that exposes that CLI —
> a skill alone can't shell out to another vendor. Within-CLI tier mixing is what
> this skill executes; cross-vendor is advice only unless such a bridge is present.
