# Vue3 前端（web/）—— 答辩主秀版本

> 与 `src/web/app.py`（Streamlit 版）**共用同一套 FastAPI 后端**（27 个接口），
> 二者是**同一系统的两种前端实现**：Streamlit 作为保底交付与接口验证，Vue3 作为视觉与交互主秀。

## 技术栈

| 项 | 选型 |
|---|---|
| 框架 | Vue 3（`<script setup>` + TypeScript） |
| 构建 | Vite |
| UI 库 | **Element Plus**（中文文档全、组件最全、最接近国内招聘网站观感） |
| 图表 | **ECharts**（六维雷达、簇规模环形图） |
| 路由 / 状态 | Vue Router（hash 模式）+ Pinia |
| 请求 | axios（统一拦截器：自动带 Bearer 令牌、401 自动跳登录、错误统一提示） |
| 配色 | 参考 **BOSS直聘**：主色青绿 `#00A6A7`，薪资橙 `#FF6A00`，浅灰底 + 白卡片 |

## 目录

```
web/
├── index.html              # 入口（内联 SVG favicon）
├── vite.config.ts          # 开发服务器 5173 + /api 代理到 127.0.0.1:8000
├── tsconfig.json
└── src/
    ├── main.ts             # 挂载：Element Plus + Pinia + Router + 图标
    ├── App.vue             # 根组件（刷新后恢复登录态）
    ├── styles/theme.css    # 主题：Element Plus 变量换肤 + 卡片/导航/岗位卡样式
    ├── api/
    │   ├── client.ts       # axios 实例与拦截器
    │   ├── types.ts        # 接口类型（对照后端 src/api/schemas.py 一一对应）
    │   └── index.ts        # 27 个接口的封装
    ├── stores/
    │   ├── auth.ts         # 登录态（令牌存 localStorage）
    │   └── resume.ts       # 跨页共享的"本次简历"
    ├── router/index.ts     # 路由 + 登录守卫（个人中心需登录）
    ├── layouts/AppLayout.vue   # 顶部吸顶导航 + 用户下拉
    ├── components/EChart.vue   # ECharts 轻量封装
    └── views/
        ├── LoginView.vue       # 左品牌 + 右登录/注册（分栏）
        ├── ResumeView.vue      # 粘贴 / 上传 PDF + 解析结果
        ├── JobsView.vue        # ★ 左侧筛选栏 + 右侧岗位卡列表 + 抽屉详情（雷达图 + 双口径评分）
        ├── ClustersView.vue    # ECharts 环形图 + 簇表格 + 画像查询
        ├── ChatView.vue        # 对话 + 工具轨迹时间线 + 来源
        └── ProfileView.vue     # 个人中心（5 个子页签：简历/收藏/历史/问答/设置）
```

## 运行

```bash
# 1) 先起后端（另开终端，在仓库根目录）
powershell -ExecutionPolicy Bypass -File scripts/run_api.ps1     # http://127.0.0.1:8000

# 2) 起前端
cd web
npm install                       # 已配 npmmirror 源；首次约 1~2 分钟
npm run dev                       # http://127.0.0.1:5173
```

其他命令：

```bash
npm run typecheck     # vue-tsc 类型检查
npm run build         # 产物 dist/（任务12 用 nginx 托管）
npm run preview       # 本地预览构建产物，端口 4173
```

> 开发期由 Vite **代理 `/api` → `http://127.0.0.1:8000`**，所以前端代码里不写后端地址；
> 容器部署时用环境变量 `VITE_API_BASE`（如 `http://api:8000`）覆盖。

## 已验证（2026-09-16）

| 项 | 结果 |
|---|---|
| `npm run typecheck`（vue-tsc） | ✅ 0 错误 |
| `npm run build` | ✅ 成功（557ms，产物 dist/） |
| 数据层联调（Node 直接打 21 项接口） | ✅ 21/21 通过（覆盖 6 个页面用到的全部接口） |
| **无头真实渲染**（本机 Chrome headless，6 个路由） | ✅ 全部渲染出正确内容，**控制台 0 error / 0 warning** |
| 登录态渲染 | ✅ 导航出现「个人中心」，个人中心页含统计卡与 5 个子页签 |
| 路由守卫 | ✅ 未登录访问 `#/profile` 被弹回登录页 |
| 截图 | `web/screenshots/*.png`（jobs / resume / clusters / chat / profile） |

> **说明**：以上验证由脚本完成（`puppeteer-core` + 本机 Chrome），
> 目的是在**看不见画面的情况下**确认页面真的渲染、且无运行时报错。
> **配色与排版的美观程度仍需人工确认**。

## 与 Streamlit 版的关系

| | Streamlit（`src/web/app.py`） | Vue3（`web/`） |
|---|---|---|
| 定位 | 保底交付 + 接口契约验证 | 答辩主秀 |
| 启动 | `streamlit run src/web/app.py` → 8501 | `npm run dev` → 5173 |
| 依赖 | 纯 Python | Node 工具链 |
| 自动化测试 | ✅ `tests/test_web.py`（AppTest 无头执行，10 项） | ⚠️ 暂无（已用无头渲染脚本临时验证） |
| 视觉上限 | 中 | 高 |

两套前端**调同一批接口**，因此数据与口径完全一致——这正是"前端只走 HTTP"的设计收益。
