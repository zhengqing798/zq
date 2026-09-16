# -*- coding: utf-8 -*-
"""任务11 · FastAPI 接口的请求/响应契约（Pydantic 模型）

本文件即《系统设计文档》「接口设计」一节的**可执行版本**——文档里的入参/出参与此一一对应。
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- 请求
class MatchRequest(BaseModel):
    resume_id: Optional[str] = Field(None, description="上传/粘贴简历后返回的会话 ID")
    resume_text: Optional[str] = Field(None, description="直接粘贴简历正文（与 resume_id 二选一）")
    top_n: int = Field(10, ge=1, le=50, description="返回岗位数，1~50")


class ScoreRequest(BaseModel):
    job_id: str = Field(..., description="岗位ID，如 J0123（范围 J0001~J8836）")
    resume_id: Optional[str] = Field(None, description="会话 ID")
    resume_text: Optional[str] = Field(None, description="直接粘贴简历正文")


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, description="自然语言问题")
    use_cache: bool = Field(True, description="是否使用结果缓存")


class TextParseRequest(BaseModel):
    resume_text: str = Field(..., min_length=1, description="粘贴的简历正文")


# ---------------------------------------------------------------- 响应
class ParseResponse(BaseModel):
    ok: bool = True
    resume_id: str
    来源: str
    解析字段: Dict[str, Any]
    技能列表: List[str]
    技能数: int
    证书列表: List[str] = []
    未在词典的技能: List[str] = []
    解析告警: List[str] = []


class MatchResponse(BaseModel):
    ok: bool = True
    简历摘要: Dict[str, Any]
    权重版本: str
    权重: Dict[str, float]
    推荐数: int
    打分范围: int
    耗时秒: float
    推荐: List[Dict[str, Any]]
    来源: List[str]


class ScoreResponse(BaseModel):
    ok: bool = True
    岗位: Dict[str, Any]
    规则口径: Dict[str, Any]
    模型口径: Dict[str, Any]
    差异: Optional[float] = None
    来源: List[str]


class ClusterResponse(BaseModel):
    ok: bool = True
    方案: List[str] = []
    主方案: str = ""
    簇数: int
    簇: List[Dict[str, Any]]
    各方案: Dict[str, List[Dict[str, Any]]] = {}
    来源: List[str]


class ChatResponse(BaseModel):
    ok: bool = True
    问题: str
    回答: str
    来源: List[str]
    工具轨迹: List[Dict[str, Any]]
    工具序列: str
    轮数: int
    耗时秒: float
    tokens: Dict[str, int]
    prompt版本: str
    模型: str
    缓存命中: bool
    服务耗时秒: float


class HealthResponse(BaseModel):
    ok: bool = True
    启动预加载耗时秒: Dict[str, float] = {}
    匹配引擎: Dict[str, Any] = {}
    RAG检索: Dict[str, Any] = {}
    评分模型: Dict[str, Any] = {}
    Agent: Dict[str, Any] = {}
    简历会话态: Dict[str, Any] = {}
    进程运行秒: float = 0.0


class ErrorResponse(BaseModel):
    ok: bool = False
    error: str
    hint: str = ""
