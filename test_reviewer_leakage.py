from dataclasses import fields
from reviewer import ReviewerView, FORBIDDEN_FIELDS, LLMReviewer
from gate import Decision
class C:  # minimal call/ctx stubs
    function="send_money"; args={"recipient":"X"}
class Ctx: user_task="pay bill"; messages=[]
def test_view_has_no_oracle_fields():
    assert not ({f.name for f in fields(ReviewerView)} & FORBIDDEN_FIELDS)
def test_fail_closed_on_garbage():
    assert LLMReviewer(lambda p: "not json").review(C(), Ctx()) == Decision.DENY
def test_fail_closed_on_exception():
    def boom(p): raise RuntimeError
    assert LLMReviewer(boom).review(C(), Ctx()) == Decision.DENY
def test_approve_parse():
    assert LLMReviewer(lambda p: '{"decision":"APPROVE","reason":"ok"}').review(C(), Ctx()) == Decision.APPROVE
