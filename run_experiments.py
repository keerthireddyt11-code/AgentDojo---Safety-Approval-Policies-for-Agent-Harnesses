"""M7: sweep policies x k x (user task, injection task). OFFLINE mode uses the scripted agent (harness check only).
For real runs build the pipeline with an LLM element and pass llm_fn to LLMReviewer."""
import sys, itertools
import offline_test as ot
from agentdojo.task_suite.load_suites import get_suite
from gate import FullApprove, FullEscalate, TieredPolicy
from metrics import table

def sweep(suite, policies, ks, pairs):
    res = {}
    for (pname, pol), k in itertools.product(policies.items(), ks):
        runs = []
        for ut, it in pairs:
            try:
                u, s, st = ot.run(pol, k, ut, it, suite)
                runs.append({"utility": u, "attack_succeeded": s, "escalations": st.used if st else 0, "error": False})
            except Exception:
                runs.append({"utility": False, "attack_succeeded": False, "escalations": 0, "error": True})
        res[(pname, k)] = runs
    return res

if __name__ == "__main__":
    suite = get_suite("v1.2.2", "banking")
    pairs = [("user_task_4", "injection_task_5"), ("user_task_0", "injection_task_0")]
    pol = {"full-approve": FullApprove(), "full-escalate": FullEscalate(), "tiered": TieredPolicy()}
    for row in table(sweep(suite, pol, [0, 1, 3], pairs)): print(row)
