# -*- coding: utf-8 -*-
"""任务11 · FastAPI 后端：封装 评分 / 匹配 / 聚类 / 对话 四类 API

启动：
    uvicorn src.api.main:app --host 127.0.0.1 --port 8000
    或  python -m uvicorn src.api.main:app --reload      （开发时热重载）
    一键脚本：scripts/run_api.ps1

接口一览（交互文档：http://127.0.0.1:8000/docs）
    GET  /api/health                  健康检查与各组件就绪状态
    POST /api/resume/parse            上传 PDF 或粘贴文本 → 解析字段 + 技能 + 会话 ID
    POST /api/match                   简历 → Top-N 岗位推荐（六维分 + 推荐理由）
    POST /api/score                   简历 × 指定岗位 → 规则分 + 模型分（双口径）
    GET  /api/cluster/list            全部岗位簇
    GET  /api/cluster/profile         某簇画像（规模/薪资/主要岗位与技能）
    POST /api/chat                    Agent 智能问答（带来源与工具轨迹）

设计说明见 docs/系统设计文档.md；服务层实现在 src/api/services.py。
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi import FastAPI, File, Form, HTTPException, UploadFile        # noqa: E402
from fastapi.middleware.cors import CORSMiddleware                        # noqa: E402
from fastapi.responses import JSONResponse                               # noqa: E402

from src.api import schemas                                              # noqa: E402
from src.api.services import SVC                                         # noqa: E402

app = FastAPI(
    title="岗位-简历人岗匹配推荐系统 · 后端 API",
    description="任务11 前后端集成：评分 / 匹配 / 聚类 / 对话 四类接口。"
                "所有返回均带 `来源` 字段，保证每个数字可溯源。",
    version="1.0.0",
)

# 前端（Streamlit 或本地静态页）跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # 课程演示环境：放开；生产应改为具体域名
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    t = time.time()
    SVC.preload()
    print("[startup] 预加载完成，耗时 %.1fs ｜ %s" % (time.time() - t, SVC.warm), flush=True)


def _err(e, hint=""):
    kind = type(e).__name__
    msg = str(e)
    if isinstance(e, (KeyError, ValueError, IndexError)):
        raise HTTPException(status_code=400, detail={"ok": False, "error": msg, "hint": hint})
    raise HTTPException(status_code=500, detail={"ok": False, "error": "%s: %s" % (kind, msg), "hint": hint})


# ---------------------------------------------------------------- 健康检查
@app.get("/api/health", response_model=schemas.HealthResponse, tags=["辅助"])
def health():
    """组件就绪状态与预加载耗时（演示前先打这个）"""
    return SVC.health()


# ---------------------------------------------------------------- ① 简历解析
@app.post("/api/resume/parse", response_model=schemas.ParseResponse, tags=["① 简历"])
async def resume_parse(
    file: UploadFile = File(None, description="简历 PDF（与 resume_text 二选一）"),
    resume_text: str = Form(None, description="粘贴的简历正文"),
):
    if not file and not resume_text:
        raise HTTPException(status_code=400, detail={
            "ok": False, "error": "必须提供 PDF 文件或 resume_text",
            "hint": "multipart 上传 file，或用表单字段 resume_text"})
    try:
        if file:
            data = await file.read()
            if not data:
                raise ValueError("上传文件为空")
            if len(data) > 10 * 1024 * 1024:
                raise ValueError("文件超过 10MB，请压缩后再传")
            return SVC.parse_resume(pdf_bytes=data, filename=file.filename)
        return SVC.parse_resume(text=resume_text)
    except HTTPException:
        raise
    except Exception as e:
        _err(e, "PDF 解析失败时可用粘贴文本通路（两条通路共用同一解析器）")


@app.post("/api/resume/parse_text", response_model=schemas.ParseResponse, tags=["① 简历"])
def resume_parse_text(req: schemas.TextParseRequest):
    """纯 JSON 版简历解析（前端不方便用 multipart 时用）"""
    try:
        return SVC.parse_resume(text=req.resume_text)
    except Exception as e:
        _err(e)


# ---------------------------------------------------------------- ② 人岗匹配
@app.post("/api/match", response_model=schemas.MatchResponse, tags=["② 匹配"])
def match(req: schemas.MatchRequest):
    """简历 → Top-N 岗位推荐（六维分明细 + 中文推荐理由）"""
    try:
        return SVC.match(resume_id=req.resume_id, resume_text=req.resume_text, top_n=req.top_n)
    except Exception as e:
        _err(e, "先调 /api/resume/parse 拿 resume_id，或直接传 resume_text")


# ---------------------------------------------------------------- ③ 评分（双口径）
@app.post("/api/score", response_model=schemas.ScoreResponse, tags=["③ 评分"])
def score(req: schemas.ScoreRequest):
    """简历 × 指定岗位：规则六维分（主）+ 任务5 XGBoost 模型分（对照）"""
    try:
        return SVC.score(job_id=req.job_id, resume_id=req.resume_id, resume_text=req.resume_text)
    except Exception as e:
        _err(e, "job_id 形如 J0123；模型口径不可用时会返回原因，规则分仍然有效")


# ---------------------------------------------------------------- ④ 聚类
@app.get("/api/cluster/list", response_model=schemas.ClusterResponse, tags=["④ 聚类"])
def cluster_list():
    """全部岗位簇（任务7 聚类结果）"""
    try:
        return SVC.cluster_list()
    except Exception as e:
        _err(e)


@app.get("/api/cluster/profile", tags=["④ 聚类"])
def cluster_profile(name: str = ""):
    """某簇画像：规模、薪资中位数、主要岗位与技能（留空返回全部）"""
    try:
        return {"ok": True, **SVC.tool("cluster_profile", name=name or None)}
    except Exception as e:
        _err(e, "簇名可传关键词，如「软件测试」「算法」；留空返回全部簇")


# ---------------------------------------------------------------- ⑤ 对话
@app.post("/api/chat", response_model=schemas.ChatResponse, tags=["⑤ 对话"])
def chat(req: schemas.ChatRequest):
    """Agent 智能问答：Function Calling + 9 工具，答案带来源与工具轨迹"""
    try:
        return SVC.chat(req.question, use_cache=req.use_cache)
    except Exception as e:
        _err(e, "对话依赖 DeepSeek API：检查项目根目录 .env 里的 DEEPSEEK_API_KEY")


# ---------------------------------------------------------------- 错误统一格式
@app.exception_handler(HTTPException)
def _http_exc(request, exc):
    detail = exc.detail if isinstance(exc.detail, dict) else {"ok": False, "error": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content=detail)


@app.get("/", include_in_schema=False)
def index():
    return {"ok": True, "service": "岗位-简历人岗匹配推荐系统 · 后端 API",
            "docs": "/docs", "health": "/api/health",
            "接口": ["/api/resume/parse", "/api/match", "/api/score",
                   "/api/cluster/list", "/api/cluster/profile", "/api/chat"]}
