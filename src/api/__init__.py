# -*- coding: utf-8 -*-
"""任务11 · FastAPI 后端

- `main.py`      —— FastAPI 应用与路由（评分/匹配/聚类/对话）+ /api/health
- `services.py`  —— 服务层：把已有的匹配/检索/聚类/对话能力包成可调用函数（进程内单例）
- `schemas.py`   —— 接口契约（Pydantic 入参/出参，即《系统设计文档》接口设计一节的可执行版本）
- `score_features.py` —— 单对(简历,岗位) 36 维特征构造，供评分 API 调任务5 的 XGBoost 模型

启动：uvicorn src.api.main:app --host 127.0.0.1 --port 8000
文档：http://127.0.0.1:8000/docs
"""
