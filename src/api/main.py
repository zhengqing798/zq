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

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile   # noqa: E402
from fastapi.encoders import jsonable_encoder                             # noqa: E402
from fastapi.exceptions import RequestValidationError                      # noqa: E402
from fastapi.middleware.cors import CORSMiddleware                        # noqa: E402
from fastapi.responses import JSONResponse                               # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402

from src.api import db, schemas                                          # noqa: E402
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
    db.init_db()                       # 建表（首次运行自动创建 data/app.db）
    SVC.preload()
    print("[startup] 数据库就绪 ｜ 预加载完成，耗时 %.1fs ｜ %s"
          % (time.time() - t, SVC.warm), flush=True)


def _err(e, hint=""):
    kind = type(e).__name__
    msg = str(e)
    if isinstance(e, (KeyError, ValueError, IndexError, db.DBError)):
        raise HTTPException(status_code=400, detail={"ok": False, "error": msg, "hint": hint})
    raise HTTPException(status_code=500, detail={"ok": False, "error": "%s: %s" % (kind, msg), "hint": hint})


# ---------------------------------------------------------------- 认证与权限
def optional_user(authorization: str = Header(None)):
    """可选登录：带了合法 token 就返回用户，否则返回 None（用于"游客也能用，登录后存历史"）"""
    if not authorization:
        return None
    token = authorization.replace("Bearer", "").strip()
    return db.resolve_session(token)


def current_user(authorization: str = Header(None)):
    """必须登录：未登录/令牌过期 → 401"""
    if not authorization:
        raise HTTPException(status_code=401, detail={
            "ok": False, "error": "未登录", "hint": "请在请求头带 Authorization: Bearer <token>"})
    token = authorization.replace("Bearer", "").strip()
    u = db.resolve_session(token)
    if not u:
        raise HTTPException(status_code=401, detail={
            "ok": False, "error": "登录已失效或令牌无效", "hint": "请重新登录"})
    return u


def require_role(*roles):
    """角色权限控制（演示：企业功能预留，管理员可看用户列表）"""
    def dep(u=Depends(current_user)):
        if u["role"] not in roles:
            raise HTTPException(status_code=403, detail={
                "ok": False, "error": "当前角色（%s）无权访问该接口" % u["role_label"],
                "hint": "需要角色：%s" % "/".join(db.ROLE_LABEL.get(r, r) for r in roles)})
        return u
    return dep


# ---------------------------------------------------------------- 健康检查
@app.get("/api/health", response_model=schemas.HealthResponse, tags=["辅助"])
def health():
    """组件就绪状态与预加载耗时（演示前先打这个）"""
    return SVC.health()


# ================================================================ 岗位浏览（首页）
@app.get("/api/jobs/stats", response_model=schemas.JobStatsResponse, tags=["⓪ 首页"])
def jobs_stats():
    """全部 8,836 个清洗后岗位的分类统计（城市 / 大类 / 学历 / 经验 / 簇 / 热门技能）"""
    try:
        from src.api.jobs import get_store
        s = get_store().stats()
        return {"ok": True, **s}
    except Exception as e:
        _err(e)


@app.get("/api/jobs", response_model=schemas.JobListResponse, tags=["⓪ 首页"])
def jobs_list(page: int = 1, size: int = 20, city: str = "", district: str = "",
              category: str = "", keyword: str = "", salary_min: int = 0, edu: str = "",
              cluster: str = "", sort: str = "default", source_kw: str = "", seed: int = 0):
    """分页浏览全部岗位，支持城市/区县/大类/学历/关键词/薪资下限/簇/来源关键词筛选与排序

    `sort=default`（默认）时用 `seed` 做**种子随机打乱**：同 seed 翻页顺序稳定，
    换 seed 就是新顺序（前端每次进「岗位」页/重新点默认排序都会换一个 seed）。
    """
    try:
        from src.api.jobs import get_store
        r = get_store().query(page=page, size=size, city=city or None, district=district or None,
                              category=category or None, keyword=keyword or None,
                              salary_min=salary_min or None, edu=edu or None,
                              cluster=cluster or None, sort=sort, source_kw=source_kw or None,
                              seed=seed or None)
        r["来源"] = ["zhaopin_jobs_cleaned_seg.csv（清洗后 %d 个岗位）" % r["总数"]]
        return {"ok": True, **r}
    except Exception as e:
        _err(e, "筛选参数拼错时会忽略该条件；size 上限 100")


@app.get("/api/jobs/{job_id}", tags=["⓪ 首页"])
def job_detail(job_id: str):
    """单个岗位详情（含职位描述全文与所属簇）"""
    try:
        from src.api.jobs import get_store
        x = get_store().get(job_id)
        if not x:
            raise ValueError("岗位不存在：%s（有效范围 J0001 ~ J8836）" % job_id)
        return {"ok": True, **x}
    except Exception as e:
        _err(e)


# ================================================================ 首页推荐（首页改版）
@app.get("/api/home", response_model=schemas.HomeResponse, tags=["⓪ 首页"])
def home(n: int = 8):
    """首页推荐：热门分类轮播（来源关键词）/ 地区推荐 / 高薪岗位 / 热门岗位 / 热门企业"""
    try:
        from src.api.jobs import get_store
        return {"ok": True, **get_store().home(hot_n=max(1, min(int(n), 20)))}
    except Exception as e:
        _err(e)


# ================================================================ 公司浏览（公司页）
@app.get("/api/companies/stats", response_model=schemas.CompanyStatsResponse, tags=["⓪ 首页"])
def companies_stats():
    """4,096 家公司的分类统计（规模分档 / 按城市 / 按大类 / 热门企业 / 最活跃企业）"""
    try:
        from src.api.jobs import get_store
        s = get_store().company_stats()
        return {"ok": True, **s}
    except Exception as e:
        _err(e)


@app.get("/api/companies", response_model=schemas.CompanyListResponse, tags=["⓪ 首页"])
def companies_list(page: int = 1, size: int = 20, city: str = "", category: str = "",
                   keyword: str = "", bucket: str = "", sort: str = "jobs_desc"):
    """分页浏览全部公司，支持城市/大类/规模分档/公司名关键词筛选与排序"""
    try:
        from src.api.jobs import get_store
        r = get_store().company_query(page=page, size=size, city=city or None,
                                      category=category or None, keyword=keyword or None,
                                      bucket=bucket or None, sort=sort)
        r["来源"] = ["zhaopin_jobs_cleaned_seg.csv（公司名称去重）"]
        return {"ok": True, **r}
    except Exception as e:
        _err(e, "筛选参数拼错时会忽略该条件；size 上限 100")


@app.get("/api/companies/{company_id}", tags=["⓪ 首页"])
def company_detail(company_id: str):
    """单个公司详情：档案 + 全部在招岗位 + 相似公司（传 C+8位公司ID，兼容公司名）"""
    try:
        from src.api.jobs import get_store
        x = get_store().company_get(company_id)
        if not x:
            raise ValueError("公司不存在：%s（可先调 /api/companies 取 公司ID）" % company_id)
        return {"ok": True, **x}
    except Exception as e:
        _err(e)


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
def match(req: schemas.MatchRequest, user=Depends(optional_user)):
    """简历 → Top-N 岗位推荐（六维分明细 + 中文推荐理由）。

    · 未登录：直接用 resume_id / resume_text
    · 已登录：可传 `saved_resume_id` 用"个人中心里保存的简历"，并把本次推荐存入匹配历史
    """
    try:
        rid, rtext = req.resume_id, req.resume_text
        title = ""
        if getattr(req, "saved_resume_id", None):
            if not user:
                raise ValueError("使用 saved_resume_id 需先登录")
            row = [r for r in db.list_resumes(user["id"]) if r["id"] == req.saved_resume_id]
            if not row:
                raise ValueError("保存的简历不存在或无权访问：id=%s" % req.saved_resume_id)
            title, rtext, rid = row[0]["title"], row[0]["text"], None
        out = SVC.match(resume_id=rid, resume_text=rtext, top_n=req.top_n)
        if user:
            db.add_match(user["id"], title or "临时简历", req.top_n,
                         out["简历摘要"]["姓名"], out["推荐"])
            out["已存历史"] = True
        return out
    except Exception as e:
        _err(e, "先调 /api/resume/parse 拿 resume_id，或直接传 resume_text；登录用户可用 saved_resume_id")


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
def chat(req: schemas.ChatRequest, user=Depends(optional_user)):
    """Agent 智能问答：Function Calling + 12 工具，答案带来源与工具轨迹

    · `use_cache=false` → 忽略缓存、强制真实调用大模型（前端「重新回答」用这个）
    · `history=[{role,content}...]` → 带上最近几轮对话，支持追问
    · 登录后自动把问答写入问答记录
    """
    try:
        out = SVC.chat(req.question, use_cache=req.use_cache, history=req.history)
        if user:
            db.add_chat(user["id"], req.question, out["回答"], out["来源"], out["工具序列"])
            out["已存历史"] = True
        return out
    except Exception as e:
        _err(e, "对话依赖 DeepSeek API：检查项目根目录 .env 里的 DEEPSEEK_API_KEY")


# ================================================================ 用户体系
@app.post("/api/auth/register", response_model=schemas.TokenResponse, tags=["⑥ 用户"])
def register(req: schemas.RegisterRequest):
    """注册（成功后直接返回登录令牌，前端可免二次登录）"""
    try:
        u = db.create_user(req.username, req.password, req.role,
                           req.nickname, req.phone, req.email)
        token, exp = db.create_session(u["id"])
        return {"ok": True, "token": token, "expires_at": exp, "用户": u}
    except Exception as e:
        _err(e, "用户名 3~24 位字母/数字/下划线，密码至少 6 位")


@app.post("/api/auth/login", response_model=schemas.TokenResponse, tags=["⑥ 用户"])
def login(req: schemas.LoginRequest):
    try:
        u = db.verify_user(req.username, req.password)
        if not u:
            raise HTTPException(status_code=401, detail={
                "ok": False, "error": "用户名或密码错误", "hint": "注意区分大小写"})
        token, exp = db.create_session(u["id"])
        return {"ok": True, "token": token, "expires_at": exp, "用户": u}
    except HTTPException:
        raise
    except Exception as e:
        _err(e)


@app.post("/api/auth/logout", tags=["⑥ 用户"])
def logout(authorization: str = Header(None)):
    if authorization:
        db.delete_session(authorization.replace("Bearer", "").strip())
    return {"ok": True}


@app.get("/api/auth/me", response_model=schemas.UserResponse, tags=["⑥ 用户"])
def me(user=Depends(current_user)):
    return {"ok": True, "用户": user}


@app.put("/api/user/profile", response_model=schemas.UserResponse, tags=["⑥ 用户"])
def update_profile(req: schemas.UpdateProfileRequest, user=Depends(current_user)):
    try:
        return {"ok": True, "用户": db.update_profile(user["id"], req.nickname, req.phone, req.email)}
    except Exception as e:
        _err(e)


@app.put("/api/user/password", tags=["⑥ 用户"])
def change_password(req: schemas.ChangePasswordRequest, user=Depends(current_user)):
    try:
        db.change_password(user["id"], req.old_password, req.new_password)
        return {"ok": True, "message": "密码已修改，请用新密码重新登录"}
    except Exception as e:
        _err(e, "需提供正确的原密码；新密码至少 6 位")


@app.get("/api/user/stats", response_model=schemas.StatsResponse, tags=["⑥ 用户"])
def user_stats(user=Depends(current_user)):
    return {"ok": True, "统计": db.user_stats(user["id"]), "用户": user}


# ---------------------------------------------------------------- 个人中心：简历（一人一份）
@app.get("/api/user/resumes", response_model=schemas.ResumeListResponse, tags=["⑦ 个人中心"])
def list_resumes(user=Depends(current_user)):
    """一个用户只有一份简历，所以「简历」数组正常是 0 或 1 条"""
    return {"ok": True, "简历": db.list_resumes(user["id"])}


@app.post("/api/user/resumes", tags=["⑦ 个人中心"])
def create_resume(req: schemas.ResumeCreateRequest, user=Depends(current_user)):
    """保存简历：**已有就覆盖更新**，没有才新建（一个用户始终只有一份）"""
    try:
        rid, created = db.save_resume(user["id"], req.title, req.text, req.is_default)
        return {"ok": True, "id": rid, "message": "简历已保存" if created else "简历已更新"}
    except Exception as e:
        _err(e)


@app.put("/api/user/resumes/{rid}", tags=["⑦ 个人中心"])
def edit_resume(rid: int, req: schemas.ResumeUpdateRequest, user=Depends(current_user)):
    try:
        db.update_resume(user["id"], rid, req.title, req.text)
        return {"ok": True, "message": "已更新"}
    except Exception as e:
        _err(e)


@app.put("/api/user/resumes/{rid}/default", tags=["⑦ 个人中心"])
def make_default(rid: int, user=Depends(current_user)):
    try:
        db.set_default_resume(user["id"], rid)
        return {"ok": True, "message": "已设为默认简历"}
    except Exception as e:
        _err(e)


@app.delete("/api/user/resumes/{rid}", tags=["⑦ 个人中心"])
def remove_resume(rid: int, user=Depends(current_user)):
    try:
        db.delete_resume(user["id"], rid)
        return {"ok": True, "message": "已删除"}
    except Exception as e:
        _err(e)


# ---------------------------------------------------------------- 个人中心：收藏
@app.get("/api/user/favorites", tags=["⑦ 个人中心"])
def list_favorites(user=Depends(current_user)):
    return {"ok": True, "收藏": db.list_favorites(user["id"])}


@app.post("/api/user/favorites", tags=["⑦ 个人中心"])
def add_favorite(req: schemas.FavoriteRequest, user=Depends(current_user)):
    """收藏岗位：只传 job_id，岗位信息由后端查真值补齐（保证与岗位库一致）"""
    try:
        ji = int(str(req.job_id).upper().lstrip("J")) - 1
        idx, _, _, _, _ = SVC.matcher
        if not (0 <= ji < len(idx)):
            raise ValueError("岗位ID 超出范围（有效范围 J0001 ~ J%04d）" % len(idx))
        row = idx.rows[ji]
        db.add_favorite(user["id"], "J%04d" % (ji + 1), row["岗位名称"], row["公司名称"],
                        (row["岗位地区"] or "").split()[0] if (row["岗位地区"] or "").split() else "",
                        row["岗位薪资"], req.note)
        return {"ok": True, "message": "已收藏 %s" % row["岗位名称"]}
    except Exception as e:
        _err(e, "job_id 形如 J0123")


@app.delete("/api/user/favorites/{job_id}", tags=["⑦ 个人中心"])
def remove_favorite(job_id: str, user=Depends(current_user)):
    try:
        db.delete_favorite(user["id"], job_id)
        return {"ok": True, "message": "已取消收藏"}
    except Exception as e:
        _err(e)


# ---------------------------------------------------------------- 个人中心：历史
@app.get("/api/user/matches", tags=["⑦ 个人中心"])
def list_matches(limit: int = 20, user=Depends(current_user)):
    return {"ok": True, "历史": db.list_matches(user["id"], limit)}


@app.get("/api/user/chats", tags=["⑦ 个人中心"])
def list_chats(limit: int = 20, user=Depends(current_user)):
    return {"ok": True, "历史": db.list_chats(user["id"], limit)}


# ---------------------------------------------------------------- 权限演示：仅管理员
@app.get("/api/admin/users", tags=["⑧ 权限演示"])
def admin_users(user=Depends(require_role("admin"))):
    """仅管理员可访问——用于演示角色权限控制（普通用户会收到 403）"""
    return {"ok": True, "用户数": len(db.list_users()), "用户": db.list_users()}


# ---------------------------------------------------------------- 错误统一格式
@app.exception_handler(StarletteHTTPException)
def _http_exc(request, exc):
    """统一错误体：`{"ok": false, "error": "...", "hint": "..."}`

    为什么注册在 **Starlette** 的 HTTPException 上而不是 FastAPI 的：
      · 路由没匹配上（404 Not Found）和方法不允许（405 Method Not Allowed）抛的是
        **Starlette** 的 HTTPException，不是 FastAPI 的子类；
      · 原来只注册 FastAPI 那一个，这两类错误就绕过了统一处理器，直接返回
        `{"detail": "Not Found"}` —— 客户端得同时兼容两种错误体结构；
      · 注册在父类上，FastAPI 的 HTTPException 也会命中（异常处理器按 MRO 查找）。
    见《测试报告》缺陷 15。
    """
    detail = exc.detail if isinstance(exc.detail, dict) else {
        "ok": False, "error": str(exc.detail),
        "hint": "请求的地址或方法不对；接口清单见 /docs"}
    return JSONResponse(status_code=exc.status_code, content=detail)


# Pydantic 的校验类型 → 中文说明。
# `type` 是稳定的机器标识，比去解析 msg 字符串可靠（msg 会随 Pydantic 版本变）。
_VALIDATION_ZH = {
    "missing": "缺少必填参数",
    "string_too_short": "长度不足",
    "string_too_long": "长度超过上限",
    "string_type": "必须是字符串",
    "int_parsing": "必须是整数",
    "int_type": "必须是整数",
    "float_parsing": "必须是数字",
    "float_type": "必须是数字",
    "bool_parsing": "必须是 true 或 false",
    "bool_type": "必须是 true 或 false",
    "list_type": "必须是数组",
    "dict_type": "必须是对象",
    "json_invalid": "请求体不是合法 JSON",
    "greater_than": "须大于限定值",
    "greater_than_equal": "小于允许的最小值",
    "less_than": "须小于限定值",
    "less_than_equal": "超过允许的最大值",
    "string_pattern_mismatch": "格式不符合要求",
    "enum": "取值不在允许的选项内",
    "extra_forbidden": "出现了不支持的参数",
    "value_error": "取值不合法",
}


def _zh_validation_error(e):
    """把一条 Pydantic 校验错误翻成人话（并带上约束数值，用户能照着改）

    为什么要翻译：前端 `client.ts` 会把 `error` 原样弹给用户，
    而 Pydantic 的 `msg` 是英文（`Input should be less than or equal to 50`）。
    只拼接英文原文等于把"原始 JSON"换成"夹着英文的句子"，没有真正解决。
    """
    loc = [str(x) for x in e.get("loc", []) if x not in ("body", "query", "path")]
    field = ".".join(loc) or "请求体"
    text = _VALIDATION_ZH.get(e.get("type", ""), "取值不合法（%s）" % e.get("msg", ""))
    ctx = e.get("ctx") or {}
    limits = []
    for key, label in (("ge", "最小"), ("gt", "须大于"), ("le", "上限"), ("lt", "须小于"),
                       ("min_length", "最短"), ("max_length", "最长")):
        if key in ctx:
            limits.append("%s %s" % (label, ctx[key]))
    if limits:
        text += "（%s）" % "，".join(limits)
    return "%s：%s" % (field, text)


@app.exception_handler(RequestValidationError)
def _validation_exc(request, exc):
    """把 Pydantic 的参数校验错误（422）也纳入统一错误体

    为什么必须改：FastAPI 默认的 422 响应体是
        {"detail": [{"type": "string_too_long", "loc": ["body", "question"],
                     "msg": "String should have at most 500 characters", ...}]}
      · 结构与本项目其它错误的 `{"ok", "error", "hint"}` **不一致**；
      · 前端 `web/src/api/client.ts` 的错误处理里，`detail` 是数组时落到
        `JSON.stringify(detail)` 分支 —— 于是**把这段英文 JSON 原样弹给用户**。
    实测可达：悬浮球的输入框原来没有 maxlength，粘贴一条超过 500 字的问题就会命中 422，
    用户看到的就是一串英文 JSON（前端已同步加 maxlength 兜住这个入口）。
    见《测试报告》缺陷 15。
    """
    items = [_zh_validation_error(e) for e in exc.errors()]
    return JSONResponse(status_code=422, content={
        "ok": False,
        "error": "参数校验失败 —— " + "；".join(items[:3]),
        "hint": "请检查参数类型与取值范围（各接口的约束见 /docs）",
        "校验明细": jsonable_encoder(exc.errors()),
    })


@app.get("/", include_in_schema=False)
def index():
    return {"ok": True, "service": "岗位-简历人岗匹配推荐系统 · 后端 API",
            "docs": "/docs", "health": "/api/health",
            "接口": ["/api/resume/parse", "/api/match", "/api/score",
                   "/api/cluster/list", "/api/cluster/profile", "/api/chat"]}
