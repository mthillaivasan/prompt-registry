# Build Execution Protocols — Prompt Registry Refactor

**Version 1.0 — 20 April 2026**
Companion to `REFACTOR_PLAN.md`. Operational discipline for running the refactor.

---

## 1. Using this alongside the plan

`REFACTOR_PLAN.md` defines **what** to do. This document defines **how** to do it safely.

Read once. Refer back when starting a new block type or when Claude Code's behaviour feels off. Do not delete or skip the principles section of the plan — it is what Claude Code re-reads every session to stay aligned with the configuration-first commitment. The principles are the refactor's enforcement mechanism, not its preamble.

---

## 2. Risk tiering of blocks

Not every block carries the same risk. Four tiers, each with its own protocol.

| Tier | Description | Blocks |
|---|---|---|
| **A — Chat only** | Thinking work done in conversation; committed to repo as a final artefact | 2, 3, 4 |
| **B — Autonomous Claude Code** | Plan → execute → commit with light approval | 1, 5, 8, 11, 12, 14, 17, 19, 21 |
| **C — Reviewed Claude Code** | Plan → approve → execute → COMMIT READY → review diff → approve → commit | 6, 13, 15, 16, 18, 20, 22, parts of 10 |
| **D — Tight control** | One file at a time, test gates between files, step-through review | 9, migration in 7, UI/API portions of 10 |

The two blocks most likely to cause serious trouble are 7 (schema migration) and 9 (Build engine rewrite). Give them the slowest protocol and do not let pace pressure drag them down the tier ladder.

---

## 3. Protocols by tier

### Tier A — Chat only

Done with chat Claude. Claude Code is used only to commit the finished artefact. No live code changes in the session. Good for Blocks 2, 3, 4, where the work is reading standards, making allocations, and producing seed files.

Procedure:

1. Open a new chat, paste the restart template (plan Section 8).
2. Do the thinking work with chat Claude.
3. At session end, save the output (YAML or MD) to a file.
4. Switch to Claude Code in the repo: *"Commit this file. Do not modify anything else."*
5. Approve the commit. Close.

### Tier B — Autonomous Claude Code

Claude Code works through the block with light-touch approval. Good for documentation blocks, spec blocks, and self-contained smoke tests.

Procedure:

1. Paste restart template including the block spec.
2. Claude Code acknowledges and proposes a one-line plan.
3. Approve → Claude Code executes and commits.
4. Review commit at end of block.

### Tier C — Reviewed Claude Code

Standard protocol. Applies to new code that integrates with existing code but does not rewrite it. Most "build something new" blocks live here.

Procedure:

1. Paste restart template.
2. Claude Code proposes a detailed plan: approach, files touched, test strategy.
3. Review or push back. When in doubt, paste the plan into chat for a second opinion.
4. Approve → Claude Code executes.
5. Tests run automatically.
6. Claude Code produces `COMMIT READY` block with diff.
7. Review diff, approve, commit.
8. Move to next task.

### Tier D — Tight control

For blocks that rewrite existing code or run migrations. Slowest protocol. Essential for the highest-risk blocks — do not shortcut.

Procedure:

1. Paste restart template with explicit *"Tier D protocol"*.
2. Claude Code reads all relevant files before proposing anything.
3. Claude Code proposes a plan at the level of individual files (not the whole block).
4. Review the file-by-file plan. Chat review mandatory before approval.
5. Approve one file to start.
6. Claude Code writes that one file.
7. Tests run — must pass before moving on.
8. `COMMIT READY` per file, not per block.
9. Diff review per file.
10. Approve, commit, move to next file.
11. If any file breaks tests, **stop and ask**. Do not patch over.

---

## 4. Chat Claude vs Claude Code — the split

| Task type | Tool |
|---|---|
| Reading standards, thinking through allocations, drafting specs | Chat Claude |
| Reading the codebase to understand what is there | Claude Code (direct repo access) |
| Writing code, running tests, creating or modifying repo files | Claude Code |
| Reviewing Claude Code's proposed plan before execution | Chat Claude (paste plan, ask for pushback) |
| Debugging conceptual or architectural issues | Chat Claude |
| Debugging broken tests | Claude Code |

**Useful pattern.** When Claude Code proposes a plan for Tier C or D, paste it into chat for a second opinion before approving. Chat Claude catches hard-coding, scope creep, and architectural drift that Claude Code may not flag on its own. The extra minute is cheap; the recovery from a bad commit is not.

---

## 5. Hard-coding failure modes

Concrete reject patterns. Claude Code will produce these by default if not checked.

| Pattern in code | Verdict | Why |
|---|---|---|
| `if dimension_id == "D2": special_logic()` | REJECT | Dimension-specific branch in code |
| `STANDARDS = {"LLM01": "Prompt injection", ...}` in a `.py` file | REJECT | Standards catalogue in code |
| `BUILD_DIMENSIONS = ["D1", "D5", "D9"]` | REJECT | Phase-to-dimension map in code |
| `def check_dimension_LLM01(prompt): ...` | REJECT | Dimension-specific function |
| `REVIEW_CADENCE_DAYS = 90` | REJECT | Cadence in code; belongs in config |
| `score = 0.9 if dim.name == "X" else 0.5` | REJECT | Per-dimension scoring in code |
| `SCORING_PROMPT_FOR_LLM01 = "Assess whether..."` | REJECT | Prompt template in code |
| `if phase == Phase.BUILD: run_engine(phase)` | ACCEPT | Phase is an enum; orchestration stays in code |
| `model.generate(prompt=dimension.scoring_prompt)` where `scoring_prompt` comes from DB | ACCEPT | Engine reads config, executes generically |
| `for dim in phase.dimensions: score(dim, prompt)` | ACCEPT | Generic loop over config-driven list |

**Rule of thumb.** If the code uses a dimension's name, a dimension's ID, or a standard's identifier as a string literal anywhere outside of seed files, it is hard-coded. This applies to tests too — tests must reference fixture-created dimensions with synthetic IDs, not production dimension IDs. A test that hard-codes `"LLM01"` is a ratchet preventing future dimension rename or standard update.

**When challenged, Claude Code will often argue "this is just the default — the table is empty otherwise" or "this is only for testing."** Both are ratchets. Reject on the first occurrence. A single accepted hard-code sets a precedent the rest of the refactor bends around.

---

## 6. Per-session starter checklist

Before any block:

- [ ] Environment verified — `pwd`, `git log --oneline -3`, `git status`
- [ ] Current block confirmed from `REFACTOR_PLAN.md`
- [ ] Tier identified (A / B / C / D)
- [ ] Protocol appropriate to tier loaded mentally
- [ ] Relevant spec files present in repo (`ARCHITECTURE.md` plus any block-specific)
- [ ] For Tier D: intent and pushback points written before any code begins
- [ ] For Tier C and D: restart template pasted so Claude Code sees principles and block spec

---

## 7. Minimum context for Claude Code at session start

Regardless of tier, Claude Code needs:

- The restart template (plan Section 8)
- The current block number and done state
- `REFACTOR_PLAN.md` readable in repo

For Tier C and D, additionally:

- `ARCHITECTURE.md` readable in repo (once produced in Phase 0)
- The block-specific spec file (for example `REFACTOR_BUILD.md` for Block 9, `SCHEMA_V2.md` for Block 7)
- The most recent `VALIDATION_LOG.md` entry if resuming a block mid-flight

For Tier D specifically, also:

- Explicit list of files Claude Code may touch in this session (scope containment)
- Explicit list of tests that must pass before moving to the next file

---

## 8. Escalation triggers

### Claude Code must stop and ask when

- Tests fail after a change — do not patch, stop
- A file requires more than 20 lines of rewrite (re-plan at smaller scope)
- Work strays outside the block's stated scope
- Schema or API contract would change beyond what the block authorises
- Any hard-coding concern is surfaced by the pattern table in Section 5
- Seed data would need to change structure (not just values) — this is a schema change in disguise

### Murali must stop and ask chat Claude when

- Claude Code proposes Tier D work without a file-by-file plan
- A block takes more than three sessions without closing — re-scope in chat
- Pushback from Claude Code starts to sound like scope creep (*"we'll also need to..."*)
- Validation log entries accumulate without being addressed
- Two consecutive blocks produce unexpected commits that needed fixing after the fact — the protocol is not holding; re-review

---

## 9. Pace expectations

A realistic mental model for the 22 blocks at 1–2 hour sessions:

- Phase 0 (Blocks 1–5): 4 to 6 sessions. Most are chat work ending in one commit.
- Phase 1 (Blocks 6–7): 3 to 5 sessions. Block 7 is the first high-risk block.
- Phase 2 (Blocks 8–11): 5 to 8 sessions. Block 9 is the single biggest block in the plan and may span 3 sessions on its own.
- Phase 3 (Blocks 12–16): 6 to 9 sessions. New code, lower per-block risk, more blocks.
- Phase 4 (Blocks 17–18): 2 to 3 sessions.
- Phase 5 (Blocks 19–20): 3 to 5 sessions.
- Phase 6 (Blocks 21–22): 2 to 3 sessions.

Total range: **25 to 39 sessions**. At 4 sessions per week that is 6 to 10 weeks. The plan is not a sprint. Discipline compounds; shortcuts do not.

---

*End of protocols.*
