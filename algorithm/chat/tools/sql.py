import os
import re
import datetime
from typing import Callable

from lazyllm import pipeline
from lazyllm.module import ModuleBase
from lazyllm.components import ChatPrompter
from lazyllm.tools.utils import chat_history_to_str
from lazyllm.tools.sql import SqlManager

from chat.component.tools.encrypt_sql_manager import EncryptSqlManager


ENCRYPT_SQL_MANAGER = os.getenv('ENCRYPT_SQL_MANAGER') == 'True'
SQLManager = EncryptSqlManager if ENCRYPT_SQL_MANAGER else SqlManager


sql_query_instruct_template = """
Given the following SQL tables and current date {current_date}, your job is to write sql queries in {db_type} given a user’s request.

{schema_desc}

Alert: Just reply the sql query in a code block start with triple-backticks and keyword "sql"
"""  # noqa E501


mongodb_query_instruct_template = """
Current date is {current_date}.
You are a seasoned expert with 10 years of experience in crafting NoSQL queries for {db_type}. 
I will provide a collection description in a specified format. 
Your task is to analyze the user_question, which follows certain guidelines, and generate a NoSQL MongoDB aggregation pipeline accordingly.

{schema_desc}

Note: Please return the json pipeline in a code block start with triple-backticks and keyword "json".
"""  # noqa E501

db_explain_instruct_template = """
你是数据库讲解助手。请结合上下文，基于已执行 SQL 的真实结果，直接回答用户的问题，避免无关赘述与臆测。
#【上下文】
##聊天历史：
```
{history}
```

##库表/字段说明：
```
{schema_desc}
```

##已执行的 SQL：
```
{statement}
```

##查询结果:
```
{result}
```

#【写作要求】
1) 语言：与用户输入保持一致（input 的语言是什么你就用什么）；不要翻译或改写原始结果中的字段名与取值。
2) 目标：先给出“结论”，再给出“依据与说明”；只引用结果中确凿可见的数据。
3) 可读性：必要时用简短列表或表格展示关键信息；如需展示明细，最多展示前 10 行并注明总行数。
4) 解释：点明关键筛选条件/分组/排序/时间范围等对结论的影响，避免过多 SQL 行话。
5) 边界情况：
   - 若结果为空：明确说明“未查询到匹配数据”，并给出 1–3 条可执行的追加查询建议。
   - 若存在 NULL/缺失值/单位不一致：如实标注，不做猜测。
6) 诚信：不得编造不存在的字段或外部事实；无法从结果回答时要坦诚说明。

input:{user_query}
"""


class SqlGenSchema(ModuleBase):
    def __init__(
        self,
        return_trace: bool = False,
    ) -> None:
        super().__init__(return_trace=return_trace)

    def forward(self, databases: list[dict], **kwargs):
        database = databases[0]
        source = database.get('source', {})
        kind = source.get('kind')
        db_name = source.get('database')
        host = source.get('host', None)
        port = source.get('port', None)
        user = source.get('user', None)
        password = source.get('password', None)
        description = database.get('description', None)
        sql_manager = SQLManager(
            db_type=kind,
            host=host,
            port=port,
            user=user,
            password=password,
            db_name=db_name,
            tables_info_dict=description
        )
        return sql_manager.desc


class SqlGenerator(ModuleBase):
    EXAMPLE_TITLE = 'Here are some example: '

    def __init__(
        self,
        llm,
        sql_examples: str = '',
        sql_post_func: Callable = None,
        return_trace: bool = False,
    ) -> None:
        super().__init__(return_trace=return_trace)
        self.sql_post_func = sql_post_func

        self._pattern = re.compile(r'```sql(.+?)```', re.DOTALL)
        self.example = sql_examples

        self._llm = llm

    def extract_sql_from_response(self, str_response: str) -> str:
        matches = self._pattern.findall(str_response)
        if matches:
            extracted_content = matches[0].strip()
            return extracted_content if not self.sql_post_func else self.sql_post_func(extracted_content)
        else:
            return ''

    def forward(self, query: str, databases: list[dict], **kwargs):
        database = databases[0]
        source = database.get('source', {})
        kind = source.get('kind')
        schema_desc = SqlGenSchema().forward(databases)

        current_date = datetime.datetime.now().strftime('%Y-%m-%d')
        sql_query_instruct = sql_query_instruct_template.format(
            current_date=current_date, db_type=kind, schema_desc=schema_desc)
        query_prompter = ChatPrompter(instruction=sql_query_instruct)

        with pipeline() as ppl:
            ppl.llm_query = self._llm.share(prompt=query_prompter).used_by(self._module_id)
            ppl.sql_extractor = self.extract_sql_from_response
        return ppl(query, **kwargs)


class SqlExecute(ModuleBase):
    EXAMPLE_TITLE = 'Here are some example: '

    def __init__(
        self,
        sql_post_func: Callable = None,
        return_trace: bool = False,
    ) -> None:
        super().__init__(return_trace=return_trace)
        self.sql_post_func = sql_post_func

    def forward(self, statement: str, databases: list[dict], **kwargs):
        database = databases[0]
        source = database.get('source', {})
        kind = source.get('kind')
        db_name = source.get('database')
        host = source.get('host', None)
        port = source.get('port', None)
        user = source.get('user', None)
        password = source.get('password', None)
        description = database.get('description', None)
        sql_manager = SQLManager(
            db_type=kind,
            host=host,
            port=port,
            user=user,
            password=password,
            db_name=db_name,
            tables_info_dict=description
        )
        return sql_manager.execute_query(statement=statement)


class SqlExplain(ModuleBase):
    EXAMPLE_TITLE = 'Here are some example: '

    def __init__(
        self,
        llm,
        sql_examples: str = '',
        sql_post_func: Callable = None,
        return_trace: bool = False,
    ) -> None:
        super().__init__(return_trace=return_trace)
        self.sql_post_func = sql_post_func
        self.example = sql_examples
        self._llm = llm

    def forward(self, input: str, user_query: str, statement: str, databases: list[dict], **kwargs):
        database = databases[0]
        source = database.get('source', {})
        kind = source.get('kind')
        schema_desc = SqlGenSchema().forward(databases)
        sql_explain_instruct = db_explain_instruct_template.format(
            history=chat_history_to_str(history=kwargs.get('llm_chat_history', [])),
            db_type=kind,
            schema_desc=schema_desc,
            statement=statement,
            result=input,
            user_query=user_query
        )
        return self._llm(sql_explain_instruct, **kwargs)
