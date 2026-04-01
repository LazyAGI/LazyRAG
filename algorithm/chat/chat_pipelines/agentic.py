# flake8: noqa: E402
import asyncio
import copy
import itertools
import json
import re
import os
import yaml
from concurrent.futures import ThreadPoolExecutor
from lazyllm import LOG, bind, loop, pipeline, switch
from tenacity import retry, stop_after_attempt, wait_fixed
import sys
from pathlib import Path

base_dir = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(base_dir))

from chat.modules.engineering.load_model import get_model
from chat.modules.engineering.simple_llm import SimpleLlmComponent
from chat.prompts.agentic import (
    EVALUATOR_PROMPT,
    EXTRACTOR_PROMPT,
    GENERATE_PROMPT,
    PLANREFINE_PROMPT,
    PLANNER_PROMPT,
    TOOLCALL_PROMPT,
)
from chat.modules.engineering.tool_registry import (
    get_all_tool_schemas,
    get_tool_instance,
    get_tool_schema,
)
from chat.modules.engineering.output_parser import CustomOutputParser
from chat.modules.engineering.workflow_utils import (
    PlanStep,
    TaskContext,
    tool_schema_to_string,
)


# global params and func
TEMPERATURE = 1.0


def add_reasoning_process_stream(state: TaskContext, value: str, mode: str = 'info'):
    LOG.debug(value)
    if mode != 'debug':
        state.reasoning_process_stream.append(value)
        if isinstance(value, list):
            raise ValueError(f'value: {value}')


# llms
CONFIG_PATH = os.getenv('CONFIG_PATH', f'{base_dir}/chat/chat_pipelines/configs/auto_model.yaml')
cfg = yaml.safe_load(CONFIG_PATH)
llm = get_model('qwen3_32b_custom', cfg)
llm._prompt._set_model_configs(system='You are an intelligent assistant, \
                               strictly following user instructions to execute tasks.')
# llm_gen = SimpleLlmComponent(llm=llm)

llm_instruct = get_model('qwen3_moe_custom', cfg)
llm_instruct._prompt._set_model_configs(system='You are a task assistant, \
    and you must strictly follow the given requirements to complete the tasks.\
    The output language should be the same as the input language.')
llm_gen = SimpleLlmComponent(llm=llm_instruct)


# utils
def _parse_llm_res(res: str):
    match = re.search(r'</think\s*>(.*)', res, re.DOTALL)
    if match:
        res = match.group(1).strip()
    match = re.search(r'```json\s*(\{.*?\})\s*```', res, re.DOTALL)
    if match:
        res = match.group(1).strip()
    res = json.loads(res)
    return res

def _show_search_process(state: TaskContext, action: str = 'init'):
    LOG.debug('=' * 100 + '\n')
    LOG.debug(f'🔍 【SHOW SEARCH PROCESS】 Task ID: {state.query}, Action: {action}')
    steps = state.executed_steps
    for step in steps:
        LOG.debug(step.step_id)
        LOG.debug(step.status)
        LOG.debug(step.goal)
        LOG.debug(step.tool)
        LOG.debug(step.inference)
        LOG.debug('=' * 100 + '\n')
    steps = state.pending_steps
    for step in steps:
        LOG.debug(step.step_id)
        LOG.debug(step.status)
        LOG.debug(step.goal)
        LOG.debug(step.tool)
        LOG.debug(step.inference)
        LOG.debug('*' * 100 + '\n')


# agents
def do_search(state: TaskContext):
    params = state.global_params
    original_query = params.get('query', '')
    current_step = state.pending_steps[0]
    previous_step_result = '\n'.join(state.inferences)
    tool_name = current_step.tool
    tool_schema = get_tool_schema(tool_name)

    prompt = TOOLCALL_PROMPT.substitute(original_query=original_query,
                                        current_goal=current_step.goal,
                                        previous_step_result=previous_step_result,
                                        tool_description=tool_schema_to_string(tool_schema, include_params=True))
    res = llm_instruct(prompt, temperature=TEMPERATURE)
    res = _parse_llm_res(res)
    tool_name = res['tool']
    params = res['params']
    tool_instance = get_tool_instance(tool_name)
    if not tool_instance:
        raise ValueError(f'Unknown tool: {tool_name}')

    add_reasoning_process_stream(state, f'🔍 【RETRIEVER】 Original Query: {original_query}')
    add_reasoning_process_stream(state, f'🔍 【RETRIEVER】 Params: {params}\n')
    static_params = state.tool_params[tool_name]
    if len(state.executed_steps) == 0:
        params['querys'].append(original_query)
    raw_results, formatted_results = tool_instance(**params, static_params=static_params)
    add_reasoning_process_stream(state, f'🔍 【RETRIEVER】 Retrieved {len(formatted_results)} nodes\n')

    state.pending_steps[0].formatted_results = formatted_results
    state.pending_steps[0].raw_results = raw_results
    extract_info(state)
    _show_search_process(state, 'search')
    return state


def generate_answer(state: TaskContext):
    query = state.query
    add_reasoning_process_stream(state, f'✅ 【GENERATOR】 开始生成答案....| Query: {query}')

    nodes = state.middle_results.raw_results
    inference = '\n'.join(state.inferences)
    agg_nodes = []
    for _, grp in itertools.groupby(nodes, key=lambda x: x.global_metadata['docid']):
        grouped_nodes = list(grp)
        # group = sorted(group, key=lambda n: n.metadata['index'])
        file_contents = []
        for node in grouped_nodes:
            text = node._content
            title = node.metadata.get('title', '')
            if title:
                text = f'{title.strip()}\n{text.lstrip()}'
            file_contents.append(text)
        file_contents = '\n\n---\n\n'.join(file_contents)
        agg_nodes.append(grouped_nodes[0])
        agg_nodes[-1]._content = file_contents

    for index, node in enumerate(agg_nodes):
        state.middle_results.agg_results[index + 1] = node

    chunks = []
    for index, node in enumerate(agg_nodes):
        file_name = node.metadata.get('file_name', '')
        node_str = f'node[[{index + 1}]]:\nfile_name：{file_name}\n{node.text}\n'
        chunks.append(node_str)
    chunks = '\n'.join(chunks)

    prompt = GENERATE_PROMPT.format(query=query, chunks=chunks, inference=inference)
    stream = state.global_params.get('stream', False)
    if stream:
        result = llm_gen(prompt, stream=True, temperature=TEMPERATURE)
        asyncio.run(get_llm_res(state, result))
        add_reasoning_process_stream(state, '<END>')
        # LOG.info(f"state.reasoning_process_stream: {state.reasoning_process_stream}")
        return state
    else:
        result = llm_gen(prompt, stream=False, temperature=TEMPERATURE)
        think = ''
        answer = result
        think_match = re.search(r'(.*?)</think>', result, re.DOTALL)
        if think_match:
            think = think_match.group(1).strip()
            answer_match = re.search(r'</think>(.*)', result, re.DOTALL)
            if answer_match:
                answer = answer_match.group(1).strip()
            else:
                answer = ''
        else:
            answer = result
        state.answer = answer
        LOG.info(f'✅【GENERATOR】 生成答案: {answer}')
        add_reasoning_process_stream(state, f'{think}</think>\n')
        add_reasoning_process_stream(state, answer)
        return state


async def get_llm_res(state: TaskContext, iter):
    check_think = False
    buffer = ''
    async for chunk in iter:
        if not check_think:
            if len(buffer) < 10:
                buffer += chunk
            else:
                if '<think>' in buffer:
                    buffer = buffer.replace('<think>', '')
                else:
                    buffer += '</think>'
                LOG.info(f'buffer: {buffer}')
                add_reasoning_process_stream(state, buffer)
                check_think = True
        else:
            add_reasoning_process_stream(state, chunk)


@retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
def plan_step(state: TaskContext):
    query = state.query
    tool_schemas = get_all_tool_schemas()
    tool_description = [tool_schema_to_string(ts, include_params=False) for ts in tool_schemas.values()]
    tool_description = '\n\n'.join(tool_description)
    tool_num = len(tool_schemas)

    prompt = PLANNER_PROMPT.substitute(original_query=query, tool_description=tool_description, tool_num=tool_num)
    res = llm(prompt, temperature=TEMPERATURE)
    res = _parse_llm_res(res)
    reason = res['reason']
    plan = res['steps']

    steps = []
    for ind, step in enumerate(plan):
        steps.append(PlanStep(step_id=ind+1, goal=step['goal'], tool=step['tool']))
    state.pending_steps = steps

    add_reasoning_process_stream(state, '<think>\n')
    add_reasoning_process_stream(state, f'💡 【PLANNER】{reason}')
    plan_str = '\n'.join([f'step{ind+1}: {p["goal"]}' for ind, p in enumerate(plan)])
    add_reasoning_process_stream(state, f'💡 【PLANNER】Generated Plan:\n{plan_str}\n\n')
    _show_search_process(state)
    return state


@retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
def evaluate(state: TaskContext):
    query = state.query
    last_step = state.executed_steps[-1]
    if not last_step.formatted_results:
        state.middle_results.evaluation_result['next_step'] = 'PlanRefine'
        state.middle_results.evaluation_result['refine_reason'] = {}
        state.middle_results.evaluation_result['refine_reason']['category'] = 'inefficient_strategy'
        state.middle_results.evaluation_result['refine_reason']['subtype'] = 'The last search failed \
            to get any useful new information.'
        return state
    add_reasoning_process_stream(state, f'🎯 【EVALUATOR】 Evaluating... | Query: {query}')
    completed_plans = [f'step{step.step_id}: {step.goal} \nstatus: {step.status} \ninference: {step.inference}'
                       for step in state.executed_steps]
    pending_plans = [f'step{step.step_id}: {step.goal} \nstatus: {step.status}' for step in state.pending_steps]

    prompt = EVALUATOR_PROMPT.substitute(original_query=query,
                                         plans='\n\n'.join(completed_plans+pending_plans))
    res = llm_instruct(prompt, temperature=TEMPERATURE)
    res = _parse_llm_res(res)

    next_step = res['next_step']
    if next_step == 'GenerateAnswer':
        eval_res = {'next_step': 'GenerateAnswer'}
    elif next_step == 'PlanRefine':
        eval_res = {'next_step': 'PlanRefine', 'refine_reason': res['refine_reason']}
    else:
        eval_res = {'next_step': 'FurtherSearch'}

    add_reasoning_process_stream(state, f'🎯 【EVALUATOR】: {res["reason"]}')
    add_reasoning_process_stream(state, f'🎯 【EVALUATOR】 next step: 【{eval_res["next_step"]}】\n')
    state.middle_results.evaluation_result = eval_res
    return state


@retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
def plan_refine(state: TaskContext):
    query = state.query
    # refine_reason = state.middle_results.evaluation_result['refine_reason']['subtype']
    add_reasoning_process_stream(state, f'🎯 【PLANNERREFINER】 query: {query}\n')

    executed_plan_and_inferences = [f'plan: {step.goal} \ninference: {step.inference}' for step in state.executed_steps]
    remaining_plans = [step.goal for step in state.pending_steps]

    tool_schemas = get_all_tool_schemas()
    tool_description = [tool_schema_to_string(ts, include_params=False) for ts in tool_schemas.values()]
    tool_description = '\n\n'.join(tool_description)
    prompt = PLANREFINE_PROMPT.substitute(original_query=query,
                                          executed_plan_and_inferences='\n\n'.join(executed_plan_and_inferences),
                                          remaining_plan='\n'.join(remaining_plans),
                                          #   refine_reason=refine_reason,
                                          tool_description=tool_description)
    res = llm_instruct(prompt, temperature=TEMPERATURE)
    res = _parse_llm_res(res)
    add_reasoning_process_stream(state, f'🎯 【REVIEWER】{res["reason"]}\n')

    if not res['steps']:
        add_reasoning_process_stream(state, '🎯 【REVIEWER】 Next step: 【GenerateAnswer】\n\n')
        add_reasoning_process_stream(state, f'🎯 【REVIEWER】 Reason: {res["reason"]}\n\n')
        state.middle_results.evaluation_result['next_step'] = 'GenerateAnswer'
        return state

    current_step = len(state.executed_steps)
    new_plan_str = []
    state.pending_steps = []
    for ind, step in enumerate(res['steps']):
        state.pending_steps.append(PlanStep(step_id=current_step+ind+1, goal=step['goal'], tool=step['tool']))
        new_plan_str.append(step['goal'])
    new_plan_str = '\n'.join([f'step{idx+1}: {step}' for idx, step in enumerate(new_plan_str)])

    add_reasoning_process_stream(state, '🎯 【PLANNERREFINER】 next step：【FurtherSearch】\n')
    add_reasoning_process_stream(state, f'🎯 【PLANNERREFINER】 new plan：{new_plan_str}\n\n')
    _show_search_process(state, 'refine')
    return state


@retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
def extract_info(state: TaskContext):
    query = state.query
    add_reasoning_process_stream(state, f'🛠️ 【EXTRACTOR】 extract information... | Query: {query}')

    inference = '\n'.join(state.inferences)
    new_nodes = state.pending_steps[0].formatted_results
    raw_nodes = state.pending_steps[0].raw_results
    if not new_nodes:
        state.pending_steps[0].status = 'completed'
        state.executed_steps.append(state.pending_steps.pop(0))
        add_reasoning_process_stream(state, f'🛠️ 【EXTRACTOR】 本轮没有发现新信息... | Query: {query}\n')
        return None
    new_nodes_str = [f'NODE[[{ind}]]:\n{node}' for ind, node in enumerate(new_nodes)]
    new_nodes_str = '\n\n'.join(new_nodes_str)
    prompt = EXTRACTOR_PROMPT.substitute(original_query=query,
                                         current_step=state.pending_steps[0].goal,
                                         inference=inference,
                                         new_nodes=new_nodes_str)
    res = llm_instruct(prompt, temperature=TEMPERATURE)
    res = _parse_llm_res(res)
    new_inference = res['inference']
    if any(int(ind) >= len(new_nodes) for ind in res['relevant_nodes']):
        raise ValueError(f'🛠️ 【EXTRACTOR】 节点编号超出范围: {res["relevant_nodes"]}')
    relevant_nodes = [new_nodes[int(ind)] for ind in res['relevant_nodes']]
    raw_nodes = [raw_nodes[int(ind)] for ind in res['relevant_nodes']]

    add_reasoning_process_stream(state, f'🛠️ 【EXTRACTOR】 Reasoning process: {res["reason"]}')
    add_reasoning_process_stream(state, f'🛠️ 【EXTRACTOR】 New inference: {new_inference}\n')
    add_reasoning_process_stream(state, f'🛠️ 【EXTRACTOR】 Node indices: {res["relevant_nodes"]}', mode='debug')
    LOG.info(f'🛠️ 【EXTRACTOR】 Relevant nodes: {relevant_nodes}\n')
    # add_reasoning_process_stream(state, f'🛠️ 【EXTRACTOR】 Relevant nodes: {relevant_nodes}\n', mode='debug')

    state.inferences.append(new_inference)
    state.pending_steps[0].extracted_results = relevant_nodes  # list of str
    state.pending_steps[0].raw_results = raw_nodes
    state.pending_steps[0].inference = new_inference
    state.pending_steps[0].status = 'completed'
    state.executed_steps.append(state.pending_steps.pop(0))
    state.middle_results.formatted_results.extend(relevant_nodes)
    state.middle_results.raw_results.extend(raw_nodes)
    return state


def get_ppl_agentic():

    with pipeline() as search_eval_ppl:
        search_eval_ppl.search = do_search
        search_eval_ppl.eval = evaluate
        search_eval_ppl.divert = switch((lambda x: x.middle_results.evaluation_result['next_step'] == 'PlanRefine'),
                                        plan_refine,
                                        'default', (lambda x: x))

    with pipeline() as ppl:
        ppl.planner = plan_step
        ppl.loop = loop(
            search_eval_ppl,
            stop_condition=lambda x: x.middle_results.evaluation_result['next_step'] == 'GenerateAnswer',
            count=4,
        )
        ppl.gen = bind(generate_answer, ppl.input)

    return ppl


async def astream_iterator(agent, state):
    CHUNK_SIZE = 15
    CHUNK_DELAY = 0.1
    end = False
    seen_think = False
    with ThreadPoolExecutor(1) as executor:
        future = executor.submit(agent, state)
        while True:
            value = state.reasoning_process_stream[:]
            state.reasoning_process_stream = []
            if value:
                text = ''.join(value)
                if '<END>' in text:
                    text = text.replace('<END>', '')
                    end = True
                if '<think>' in text:
                    if not seen_think:
                        seen_think = True
                    else:
                        text = text.replace('<think>', '')
                for i in range(0, len(text), CHUNK_SIZE):
                    chunk = text[i:i + CHUNK_SIZE]
                    LOG.info(f'yielding chunk: {chunk}')
                    yield chunk
                    if i + CHUNK_SIZE < len(text):
                        await asyncio.sleep(CHUNK_DELAY)
            elif end and future.done():
                break
            else:
                await asyncio.sleep(0.1)


agent = get_ppl_agentic()


def agentic_rag(global_params, tool_params, stream=False, **kwargs):
    state = TaskContext()
    query = global_params.get('query', '')
    if not query:
        raise ValueError('query is required')
    global_params['stream'] = stream
    for key, value in kwargs.items():
        global_params[key] = value

    state.query = query
    state.global_params = global_params
    state.tool_params = tool_params
    state.middle_results.agg_results = {}
    if stream:
        as_iter = astream_iterator(agent, state)
        agg_nodes = state.middle_results.agg_results
        return CustomOutputParser().forward(as_iter, aggregate=agg_nodes, stream=True)
    else:
        try:
            state = agent(state)
        except Exception as e:
            LOG.error(f'Error: {e}')
            return {'think': '', 'text': '', 'recall': []}
        # answer = state.answer
        relevant_nodes = copy.deepcopy(state.middle_results.formatted_results)
        agg_nodes = copy.deepcopy(state.middle_results.agg_results)
        answer = '\n'.join(state.reasoning_process_stream)
        # round_num = len(state.executed_steps)
        LOG.info(f'agg_nodes: {agg_nodes}')
        res = CustomOutputParser().forward(answer, aggregate=agg_nodes, stream=False)
        res['recall'] = relevant_nodes
        return res  # , relevant_nodes, round_num
