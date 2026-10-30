"""Approval gate for AgentDojo (prototype verified against agentdojo 0.1.35)."""
from __future__ import annotations
import enum, re
from dataclasses import dataclass, field
from collections.abc import Sequence
from typing import Callable

from agentdojo.agent_pipeline import BasePipelineElement, ToolsExecutor
from agentdojo.agent_pipeline.tool_execution import tool_result_to_str
from agentdojo.functions_runtime import EmptyEnv, Env, FunctionsRuntime, FunctionCall
from agentdojo.types import ChatMessage, ChatToolResultMessage, text_content_block_from_string


class Decision(str, enum.Enum):
    APPROVE = "APPROVE"
    DENY = "DENY"
    ESCALATE = "ESCALATE"


@dataclass
class GateState:
    k: int
    used: int = 0
    records: list[dict] = field(default_factory=list)


class GateInit(BasePipelineElement):
    """First element: gives every task a fresh GateState (pipeline objects are reused across tasks)."""
    name = "gate_init"

    def __init__(self, k: int):
        self.k = k

    def query(self, query, runtime, env=EmptyEnv(), messages=[], extra_args={}):
        return query, runtime, env, messages, {"gate": GateState(k=self.k)}   # NEW dict, never mutate the default


@dataclass
class Context:
    user_task: str
    messages: Sequence[ChatMessage]
    used: int
    k: int
    env: object = None


class GatedToolsExecutor(ToolsExecutor):
    def __init__(self, policy, reviewer, **kw):
        super().__init__(**kw)
        self.policy, self.reviewer = policy, reviewer

    def query(self, query, runtime: FunctionsRuntime, env: Env = EmptyEnv(), messages=[], extra_args={}):
        if not messages or messages[-1]["role"] != "assistant" or not messages[-1]["tool_calls"]:
            return query, runtime, env, messages, extra_args
        state: GateState = extra_args["gate"]
        results = []
        for call in messages[-1]["tool_calls"]:
            ctx = Context(user_task=query, messages=messages, used=state.used, k=state.k, env=env)
            proposed = self.policy.decide(call, ctx)
            final, reason = proposed, "policy"
            if proposed == Decision.ESCALATE:
                if state.used < state.k:
                    state.used += 1
                    final = self.reviewer.review(call, ctx)
                    reason = "reviewer"
                else:
                    final, reason = Decision.DENY, "budget exhausted"
            state.records.append({"tool": call.function, "args": dict(call.args),
                                  "proposed": proposed.value, "final": final.value,
                                  "by": reason, "used": state.used})
            if final == Decision.APPROVE:
                out, err = runtime.run_function(env, call.function, call.args)
                content, error = self.output_formatter(out), err
            else:
                content, error = "", f"Blocked by approval policy ({reason}). Do not retry this call."
            results.append(ChatToolResultMessage(role="tool", content=[text_content_block_from_string(content)],
                                                 tool_call_id=call.id, tool_call=call, error=error))
        return query, runtime, env, [*messages, *results], extra_args


# ---------------- policies ----------------
class FullApprove:
    def decide(self, call, ctx): return Decision.APPROVE

class FullEscalate:
    def decide(self, call, ctx): return Decision.ESCALATE

READ_ONLY = {"get_iban", "get_balance", "get_most_recent_transactions",
             "get_scheduled_transactions", "read_file", "get_user_info"}
MONEY_OUT = {"send_money", "schedule_transaction", "update_scheduled_transaction"}
ACCOUNT_WRITE = {"update_password", "update_user_info"}
IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")

def _text(m):  # flatten a message's text blocks
    return " ".join(b.get("content", "") for b in m["content"] if b["type"] == "text")

def trusted_text(ctx) -> str:
    """User prompt + results of the user's OWN data tools. File contents are NOT trusted."""
    parts = [ctx.user_task]
    for m in ctx.messages:
        if m["role"] == "tool" and m["tool_call"].function in {"get_iban", "get_scheduled_transactions"}:
            parts.append(_text(m))
    return " ".join(parts)

def untrusted_text(ctx) -> str:
    return " ".join(_text(m) for m in ctx.messages
                    if m["role"] == "tool" and m["tool_call"].function in {"read_file", "get_most_recent_transactions"})

class TieredPolicy:
    """Route-A style provenance policy for the banking suite."""
    def decide(self, call: FunctionCall, ctx: Context) -> Decision:
        if call.function in READ_ONLY:
            return Decision.APPROVE
        if call.function in ACCOUNT_WRITE:
            return Decision.ESCALATE
        if call.function == "update_scheduled_transaction" and not call.args.get("recipient"):
            return Decision.ESCALATE               # amount-only change to an existing standing order
        if call.function in MONEY_OUT:
            payee = str(call.args.get("recipient", ""))
            if payee and payee in trusted_text(ctx):
                return Decision.APPROVE            # payee named by the user or in own data
            if payee and payee in untrusted_text(ctx):
                return Decision.ESCALATE           # only seen in untrusted content: ambiguous
            return Decision.DENY                   # appears nowhere the agent legitimately saw
        return Decision.ESCALATE                   # unknown tool

# ---------------- reviewer test double ----------------
class RuleReviewer:
    """Offline stand-in for the LLM reviewer: approves only payees the user named. NOT used for evaluation."""
    def review(self, call, ctx):
        payee = str(call.args.get("recipient", ""))
        return Decision.APPROVE if payee and payee in ctx.user_task else Decision.DENY
