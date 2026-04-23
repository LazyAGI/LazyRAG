import asyncio
import importlib
import sys
from types import ModuleType, SimpleNamespace


def _import_agentic_module(monkeypatch):
    fake_lazyllm = ModuleType('lazyllm')
    fake_lazyllm.LOG = SimpleNamespace(
        info=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )
    fake_lazyllm.bind = lambda *args, **kwargs: ('bind', args, kwargs)
    fake_lazyllm.loop = lambda *args, **kwargs: ('loop', args, kwargs)
    fake_lazyllm.pipeline = lambda *args, **kwargs: None
    fake_lazyllm.switch = lambda *args, **kwargs: ('switch', args, kwargs)

    fake_tenacity = ModuleType('tenacity')
    fake_tenacity.retry = lambda *args, **kwargs: (lambda fn: fn)
    fake_tenacity.stop_after_attempt = lambda count: count
    fake_tenacity.wait_fixed = lambda delay: delay

    fake_get_models = ModuleType('chat.pipelines.builders.get_models')
    fake_get_models.get_automodel = lambda role, wrap_simple_llm=False: f'model:{role}:{wrap_simple_llm}'

    fake_prompts = ModuleType('chat.prompts.agentic')
    template = SimpleNamespace(substitute=lambda **kwargs: '{}', format=lambda **kwargs: 'formatted')
    fake_prompts.EVALUATOR_PROMPT = template
    fake_prompts.EXTRACTOR_PROMPT = template
    fake_prompts.GENERATE_PROMPT = template
    fake_prompts.PLANREFINE_PROMPT = template
    fake_prompts.PLANNER_PROMPT = template
    fake_prompts.TOOLCALL_PROMPT = template

    fake_tool_registry = ModuleType('chat.components.tmp.tool_registry')
    fake_tool_registry.get_all_tool_schemas = lambda: {}
    fake_tool_registry.get_tool_instance = lambda name: None
    fake_tool_registry.get_tool_schema = lambda name: {}

    fake_output_parser = ModuleType('chat.components.generate.output_parser')

    class _FakeOutputParser:
        def forward(self, value, aggregate=None, stream=False):
            if stream:
                return {'stream': True, 'aggregate': aggregate}
            return {'parsed': value, 'aggregate': aggregate, 'stream': stream}

    fake_output_parser.CustomOutputParser = _FakeOutputParser

    fake_helpers = ModuleType('chat.utils.helpers')
    fake_helpers.tool_schema_to_string = lambda schema, include_params=True: 'tool-schema'

    fake_schema = ModuleType('chat.utils.schema')

    class PlanStep:
        def __init__(self, step_id, goal, tool):
            self.step_id = step_id
            self.goal = goal
            self.tool = tool
            self.status = 'pending'
            self.raw_results = []
            self.formatted_results = []
            self.extracted_results = []
            self.inference = ''

    class TaskContext:
        def __init__(self):
            self.query = ''
            self.global_params = {}
            self.tool_params = {}
            self.pending_steps = []
            self.executed_steps = []
            self.middle_results = SimpleNamespace(
                evaluation_result={},
                raw_results=[],
                formatted_results=[],
                agg_results={},
            )
            self.inferences = []
            self.reasoning_process_stream = []
            self.answer = ''

    fake_schema.PlanStep = PlanStep
    fake_schema.TaskContext = TaskContext

    for name in ['chat.pipelines.agentic']:
        sys.modules.pop(name, None)
    monkeypatch.setitem(sys.modules, 'lazyllm', fake_lazyllm)
    monkeypatch.setitem(sys.modules, 'tenacity', fake_tenacity)
    monkeypatch.setitem(sys.modules, 'chat.pipelines.builders.get_models', fake_get_models)
    monkeypatch.setitem(sys.modules, 'chat.prompts.agentic', fake_prompts)
    monkeypatch.setitem(sys.modules, 'chat.components.tmp.tool_registry', fake_tool_registry)
    monkeypatch.setitem(sys.modules, 'chat.components.generate.output_parser', fake_output_parser)
    monkeypatch.setitem(sys.modules, 'chat.utils.helpers', fake_helpers)
    monkeypatch.setitem(sys.modules, 'chat.utils.schema', fake_schema)

    return importlib.import_module('chat.pipelines.agentic')


def test_add_reasoning_process_stream_appends_non_debug_values(monkeypatch):
    module = _import_agentic_module(monkeypatch)
    state = module.TaskContext()

    module.add_reasoning_process_stream(state, 'first')
    module.add_reasoning_process_stream(state, 'hidden', mode='debug')

    assert state.reasoning_process_stream == ['first']


def test_parse_llm_res_supports_think_and_json_fence(monkeypatch):
    module = _import_agentic_module(monkeypatch)

    parsed = module._parse_llm_res('<think>ignored</think>\n```json\n{"tool":"kb","params":{"x":1}}\n```')

    assert parsed == {'tool': 'kb', 'params': {'x': 1}}


def test_agentic_rag_requires_query(monkeypatch):
    module = _import_agentic_module(monkeypatch)

    try:
        module.agentic_rag({}, {})
    except ValueError as exc:
        assert str(exc) == 'query is required'
    else:
        raise AssertionError('agentic_rag should require query')


def test_agentic_rag_non_stream_parses_agent_output(monkeypatch):
    module = _import_agentic_module(monkeypatch)

    def fake_agent(state):
        state.reasoning_process_stream = ['<think>plan</think>', 'final answer']
        state.middle_results.formatted_results = ['node-1']
        state.middle_results.agg_results = {1: 'agg-node'}
        return state

    monkeypatch.setattr(module, '_get_agent', lambda: fake_agent)

    result = module.agentic_rag({'query': 'hello'}, {'kb_search': {}}, stream=False)

    assert result == {
        'parsed': '<think>plan</think>\nfinal answer',
        'aggregate': {1: 'agg-node'},
        'stream': False,
        'recall': ['node-1'],
    }


def test_astream_iterator_yields_chunked_reasoning(monkeypatch):
    module = _import_agentic_module(monkeypatch)

    class _FakeFuture:
        def done(self):
            return True

    class _FakeExecutor:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, state):
            fn(state)
            return _FakeFuture()

    monkeypatch.setattr(module, 'ThreadPoolExecutor', _FakeExecutor)

    async def _collect():
        state = module.TaskContext()

        def _agent(inner_state):
            inner_state.reasoning_process_stream.extend(['<think>', 'abcdef', '<END>'])

        chunks = []
        async for chunk in module.astream_iterator(_agent, state):
            chunks.append(chunk)
        return chunks

    assert asyncio.run(_collect()) == ['<think>abcdef']
