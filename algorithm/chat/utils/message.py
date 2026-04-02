from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


class BaseMessage(BaseModel):
    """单轮对话消息"""
    model_config = ConfigDict(extra='forbid')

    role: Literal['user', 'assistant', 'system'] = Field(..., description='消息角色')
    content: str = Field(..., description='消息文本内容')
    time: Optional[datetime] = Field(
        default=None,
        description='消息时间（可选；ISO8601，可含时区）'
    )


class SessionMemory(BaseModel):
    """会话内已确定的实体/意图/约束"""
    model_config = ConfigDict(extra='forbid')

    topic: Optional[str] = Field(default=None, description='当前主题/任务（可选）')
    entities: List[str] = Field(default_factory=list, description='相关实体列表')
    time_hints: List[str] = Field(default_factory=list, description='相对时间线索（如：近三年、2023Q4）')
    source_scope: List[str] = Field(default_factory=list, description='限定信息源（如：公司年报、官方博客）')
