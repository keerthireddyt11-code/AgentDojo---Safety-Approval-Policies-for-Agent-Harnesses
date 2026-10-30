"""M5: simulated human reviewer. Sees ONLY a ReviewerView: no ground truth, no attack label, no injection id."""
import json, re
from dataclasses import dataclass
from pathlib import Path
from gate import Decision

@dataclass(frozen=True)
class ReviewerView:
    user_task: str      # what the user asked
    tool: str
    args: dict
    recent_tool_output: str   # last tool result, as the agent saw it

FORBIDDEN_FIELDS = {"ground_truth", "injection_task", "security", "is_attack", "goal", "utility"}
MAX_OUTPUT_CHARS = 1500

def _tool_text(m) -> str:
    """A tool message as the agent saw it: AgentDojo's LLM clients show the error INSTEAD of the content."""
    if m.get("error"):
        return f"ERROR: {m['error']}"
    return " ".join(b.get("content", "") for b in m["content"] if b["type"] == "text")

def build_view(call, ctx) -> ReviewerView:
    """Reads ONLY ctx.user_task, ctx.messages and the call. Never ctx.env or anything else."""
    last = ""
    for m in reversed(ctx.messages):
        if m["role"] == "tool":
            last = _tool_text(m)[:MAX_OUTPUT_CHARS]; break
    return ReviewerView(ctx.user_task, call.function, dict(call.args), last)

PROMPT_PATH = Path(__file__).parent / "prompts" / "reviewer_v1.txt"
PROMPT = PROMPT_PATH.read_text(encoding="utf-8").rstrip("\n")   # str.format template: {{ }} are literal braces

def render_prompt(v: ReviewerView) -> str:
    return PROMPT.format(user_task=v.user_task, tool=v.tool, args=json.dumps(v.args, default=str),
                         recent=v.recent_tool_output)

def parse_decision(text: str) -> Decision:
    """APPROVE only for a JSON object whose "decision" is exactly APPROVE (case/space-insensitive). Else DENY."""
    try:
        m = re.search(r"\{.*\}", text, re.S)
        d = json.loads(m.group(0))["decision"]
        return Decision.APPROVE if isinstance(d, str) and d.strip().upper() == "APPROVE" else Decision.DENY
    except Exception:
        return Decision.DENY

class LLMReviewer:
    """llm_fn(prompt) -> str, or -> (text, input_tokens, output_tokens). Must run at temperature 0.
    If a UsageMeter is given, llm_fn MUST return the tuple form; tokens are booked under "reviewer"."""
    def __init__(self, llm_fn, meter=None):
        self.llm_fn, self.meter = llm_fn, meter
        self._call = meter.wrap("reviewer", llm_fn) if meter is not None else llm_fn
    def review(self, call, ctx):
        try:
            out = self._call(render_prompt(build_view(call, ctx)))
            text = out[0] if isinstance(out, tuple) else out
            return parse_decision(text)
        except Exception:
            return Decision.DENY                      # fail closed
