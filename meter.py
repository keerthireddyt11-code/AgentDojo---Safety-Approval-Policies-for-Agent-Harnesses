"""M7: per-component cost accounting. Wrap every LLM call with meter.wrap(component, fn)."""
from collections import defaultdict
class UsageMeter:
    def __init__(self): self.tokens = defaultdict(lambda: {"in": 0, "out": 0})
    def wrap(self, component, fn):
        def inner(prompt, *a, **kw):
            text, tin, tout = fn(prompt, *a, **kw)      # fn must return (text, input_tokens, output_tokens)
            self.tokens[component]["in"] += tin; self.tokens[component]["out"] += tout
            return text
        return inner
    def report(self): return {c: dict(v) for c, v in self.tokens.items()}
