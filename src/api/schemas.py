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
    saved_resume_id: Optional[int] = Field(None, description="已登录用户：用个人中心保存的简历（其 id）")
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
    已存历史: Optional[bool] = Field(None, description="已登录时：本次推荐是否已写入匹配历史")


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
    已存历史: Optional[bool] = Field(None, description="已登录时：本次问答是否已写入问答记录")


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


# ================================================================ 用户体系（任务11 新增）
class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=24, description="3~24 位字母/数字/下划线")
    password: str = Field(..., min_length=6, max_length=64, description="至少 6 位")
    role: str = Field("jobseeker", description="角色：jobseeker(求职者) / employer(企业，预留) / admin")
    nickname: str = Field("", max_length=24)
    phone: str = Field("", max_length=20)
    email: str = Field("", max_length=64)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    ok: bool = True
    token: str
    expires_at: str
    用户: Dict[str, Any]


class UserResponse(BaseModel):
    ok: bool = True
    用户: Dict[str, Any]


class UpdateProfileRequest(BaseModel):
    nickname: Optional[str] = Field(None, max_length=24)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=64)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=64)


class ResumeCreateRequest(BaseModel):
    title: str = Field("", max_length=40)
    text: str = Field(..., min_length=1, description="简历正文")
    is_default: Optional[bool] = None


class ResumeUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=40)
    text: Optional[str] = Field(None, min_length=1)


class ResumeListResponse(BaseModel):
    ok: bool = True
    简历: List[Dict[str, Any]]


class FavoriteRequest(BaseModel):
    job_id: str = Field(..., description="岗位ID，如 J0123")
    note: str = Field("", max_length=200)


class StatsResponse(BaseModel):
    ok: bool = True
    统计: Dict[str, int]
    用户: Dict[str, Any]


# ================================================================ 岗位浏览（首页）
class JobListResponse(BaseModel):
    ok: bool = True
    总数: int
    页码: int
    每页: int
    总页数: int
    岗位: List[Dict[str, Any]]
    来源: List[str] = []


class JobStatsResponse(BaseModel):
    ok: bool = True
    总体: Dict[str, Any]
    按城市: List[Dict[str, Any]]
    按大类: List[Dict[str, Any]]
    按学历: List[Dict[str, Any]]
    按经验: List[Dict[str, Any]]
    按簇: List[Dict[str, Any]]
    热门技能: List[Dict[str, Any]]
    筛选项: Dict[str, Any]
    来源: List[str] = []
