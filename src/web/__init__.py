# -*- coding: utf-8 -*-
"""任务11 · Streamlit 前端

- `app.py` —— 四个页签：① 简历输入 ② 匹配推荐 ③ 岗位聚类 ④ 智能问答

启动：streamlit run src/web/app.py --server.port 8501
地址：http://127.0.0.1:8501
说明：本进程**不加载任何模型**，全部业务通过 HTTP 调 FastAPI（`API_BASE` 环境变量指定后端地址），
      因此镜像可以很小、也可以和后端分容器部署（任务12）。
"""
