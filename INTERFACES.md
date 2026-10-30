# Shared interfaces (DRAFT for A/B/C agreement)

Source of truth is the code (`gate.py`, `reviewer.py`). Where the plan doc differs, the code wins
and the difference is listed at the bottom.

## 1. Policy (owner: B) — called by the gate (owner: A)

```python
policy.decide(call: FunctionCall, ctx: Context) -> Decision   # APPROVE | DENY | ESCALATE
```

`Context` (gate.py), built fresh for every proposed call:

| field       | type                 | meaning                                       |
|-------------|----------------------|-----------------------------------------------|
| `user_task` | `str`                | the user prompt (pipeline `query`)            |
| `messages`  | `Sequence[ChatMessage]` | full conversation so far, incl. tool outputs |
| `used`      | `int`                | escalations already spent in this task        |
| `k`         | `int`                | escalation budget for this task               |
| `env`       | task environment     | live AgentDojo env (bank account, files, ...) |

`Context` carries no oracle data (no injection task, attack name, ground truth, utility/security).

## 2. Reviewer (owner: C) — called by the gate only on ESCALATE with `used < k`

```python
reviewer.review(call: FunctionCall, ctx: Context) -> Decision   # APPROVE | DENY only
```

- The reviewer must build a `ReviewerView` from `(call, ctx)` and use **only** that view:
  `user_task`, `tool`, `args`, `recent_tool_output` (last tool message text, first 1500 chars).
- It must not read `ctx.env` or anything else on `ctx`.
- Any error / unparsable output -> `DENY` (fail closed).
- The gate increments `used` **before** calling the reviewer, so a reviewer error still costs budget.

## 3. Gate log record (owner: A) — one per proposed call, in `GateState.records`

```python
{"tool": str, "args": dict, "proposed": "APPROVE|DENY|ESCALATE",
 "final": "APPROVE|DENY", "by": "policy|reviewer|budget exhausted", "used": int}
```

## 4. Per-run record (owner: A) — PROPOSED, needed by C for failure analysis

`run_experiments.py` currently keeps only `{utility, attack_succeeded, escalations, error}`.
C's failure analysis also needs:

```python
{"suite": str, "policy": str, "k": int, "user_task_id": str, "injection_task_id": str|None,
 "attack": str, "utility": bool, "attack_succeeded": bool, "escalations": int, "error": bool,
 "error_msg": str|None,
 "gate_records": [ ...section 3... ],
 "messages": [ ... ],                  # full trajectory, for example trajectories in the report
 "tokens": {"agent": {...}, "policy": {...}, "reviewer": {...}}}
```

Saved as one JSON line per run. Labels such as "was this call truly unsafe" are computed
**afterwards** by C's analysis script from the injection task and are never passed to the reviewer.

## Differences from the plan doc (code wins)

| Plan doc                         | Code                                        |
|----------------------------------|---------------------------------------------|
| `reviewer.review(view)`          | `reviewer.review(call, ctx)`; view built inside the reviewer |
| `DenyAll` control baseline       | not present in `gate.py`                    |
| UsageMeter "design"              | `meter.py` exists, not yet wired to any LLM call |
