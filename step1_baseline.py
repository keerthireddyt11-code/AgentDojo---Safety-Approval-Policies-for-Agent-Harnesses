"""M1: run ONE banking user task with a real LLM and no gate. Needs an API key (UNTESTED here: no key in this sandbox)."""
from agentdojo.agent_pipeline import AgentPipeline, PipelineConfig
from agentdojo.task_suite.load_suites import get_suite
suite = get_suite("v1.2.2", "banking")
pipe = AgentPipeline.from_config(PipelineConfig(llm="gpt-4o-2024-05-13", defense=None, system_message_name=None, system_message=None))
ut = suite.get_user_task_by_id("user_task_0")
utility, _ = suite.run_task_with_pipeline(pipe, ut, injection_task=None, injections={})
print("utility:", utility)
