import sys; sys.path.insert(0, ".")
from offline_test import *
suite = get_suite("v1.2.2", "banking")
rows = []
for ut_id in sorted(suite.user_tasks, key=lambda x: int(x.split("_")[-1])):
    ut = suite.get_user_task_by_id(ut_id)
    out = {}
    for name, pol in [("tiered", TieredPolicy()), ("full-escalate", FullEscalate())]:
        # no attack: injection_task=None; high k so nothing is starved; record escalations requested
        agent = GullibleAgent(ut, None)
        gate = GatedToolsExecutor(pol, RuleReviewer())
        p = AgentPipeline([SystemMessage("x"), InitQuery(), GateInit(99), agent, ToolsExecutionLoop([gate, agent])])
        p.name = "gpt-4o-2024-05-13"
        recs = {}
        orig = GatedToolsExecutor.query
        def spy(self, *a, **kw):
            o = orig(self, *a, **kw); recs["s"] = o[4]["gate"]; return o
        GatedToolsExecutor.query = spy
        try:
            u, _ = suite.run_task_with_pipeline(p, ut, None, {})
        finally:
            GatedToolsExecutor.query = orig
        st = recs.get("s")
        calls = len(st.records) if st else 0
        esc = sum(1 for r in st.records if r["proposed"] == "ESCALATE") if st else 0
        den = sum(1 for r in st.records if r["proposed"] == "DENY") if st else 0
        out[name] = (calls, esc, den)
    rows.append((ut_id, ut.PROMPT[:62], out))
tot = {"calls": 0, "te": 0, "td": 0, "fe": 0}
print(f"{'task':13s} calls  tiered(esc,deny)  full-esc(esc)   prompt")
for ut_id, pr, o in rows:
    c, te, td = o["tiered"]; _, fe, _ = o["full-escalate"]
    tot["calls"] += c; tot["te"] += te; tot["td"] += td; tot["fe"] += fe
    print(f"{ut_id:13s} {c:3d}    esc={te} deny={td}        {fe:2d}           {pr}")
print("TOTAL", tot)
