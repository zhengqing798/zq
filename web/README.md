# Vue3 前端（web/）—— 答辩主秀版本

> 与 `src/web/app.py`（Streamlit 版）**共用同一套 FastAPI 后端**（33 个接口），
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
    ├── utils/format.ts     # 展示层小工具（千分位、薪资「10-15K」、公司 Logo 稳定配色）
    ├── api/
    │   ├── client.ts       # axios 实例与拦截器
    │   ├── types.ts        # 接口类型（对照后端 src/api/schemas.py 一一对应）
    │   ├── jobs.ts         # 岗位浏览类型
    │   ├── companies.ts    # 公司浏览类型（公司页）
    │   └── index.ts        # 33 个接口的封装
    ├── stores/
    │   ├── auth.ts         # 登录态（令牌存 localStorage）
    │   └── resume.ts       # 跨页共享的"本次简历"
    ├── router/index.ts     # 路由 + 登录守卫（个人中心需登录）
    ├── layouts/AppLayout.vue   # 顶部吸顶导航 + 用户下拉
    ├── components/
    │   ├── EChart.vue          # ECharts 轻量封装
    │   ├── CompanyCard.vue     # 公司卡（公司列表 + 详情页「相似公司」共用）
    │   └── JobDetailDrawer.vue # ★ 职位详情抽屉（首页/公司页/公司详情三处共用）
    └── views/
        ├── LoginView.vue       # 登录/注册：整页浅青渐变 + **居中卡片**（420px），无左栏宣传面板；注册仅 3 个字段（用户名/密码/昵称，**无角色选择**）
        ├── HomeView.vue        # ★ 首页仿 BOSS直聘：城市切换 + 搜索 + 热门职位 + 筛选 + 职位卡
        ├── CompaniesView.vue   # ★ 公司广场：热门/最活跃企业榜 + 筛选 + 公司卡网格
        ├── CompanyView.vue     # ★ 公司详情：全部在招岗位 + 公司画像 + 招聘者 + 相似公司
        ├── ResumeView.vue      # 粘贴 / 上传 PDF + 解析结果
        ├── JobsView.vue        # ★ 左侧筛选栏 + 右侧岗位卡列表 + 抽屉详情（雷达图 + 双口径评分）
        ├── ChatView.vue        # 对话 + 工具轨迹时间线 + 来源
        └── ProfileView.vue     # 个人中心（5 个子页签：简历/收藏/历史/问答/设置）
```

> **已移除的页面**：`ClustersView.vue`（岗位聚类）于 2026-09-18 按使用者反馈删除——路由 `/clusters`、
> 顶部导航入口、渲染检查断言一并移除；**后端 `/api/cluster/list`、`/api/cluster/profile` 与 Streamlit 保底版聚类页保留**，
> `EChart.vue` 也被「职位推荐」页的六维雷达图继续使用，故均未删除。要恢复该页时把文件与路由加回即可。

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

## 已验证（2026-09-18）

| 项 | 结果 |
|---|---|
| `npm run typecheck`（vue-tsc） | ✅ 0 错误 |
| `npm run build` | ✅ 成功（~0.6s，产物 dist/） |
| 后端接口 | ✅ **153 项 pytest 全绿**（含新增 `tests/test_companies.py` 37 项：公司统计/列表/筛选/排序/详情/跨接口对账） |
| **无头真实渲染**（本机 Chrome headless，**8 个路由**） | ✅ 全部渲染出正确内容，**控制台 0 error**；脚本还会断言「**不该出现的内容**」——扫描范围是**全量 DOM 文本**（含隐藏页签），`岗位聚类` / `口径说明` / `职位分类导航面板` / 登录页已删的左栏文案 / 注册页的 `角色·求职者·企业` 一旦回流即报错 |
| **登录页布局几何**（一次性脚本量测 1440/1920/420 三种视口） | ✅ 卡片与品牌头水平居中（误差 ≤2px）、宽度收敛 420px（窄屏自适应 392px）、无横向滚动条、左栏面板与 PBKDF2 文案确已消失 |
| **登录流程真实点击** | ✅ 切「注册」页签 → 表单只有 3 个字段且无角色单选 → 注册成功跳转 → 新账号 `role=jobseeker`（后端默认）→ 退出后重新登录成功 → 「先以游客身份逛逛」可进首页 |
| **真实点击链路**（额外的一次性脚本验证） | ✅ 点公司卡 → 公司详情；点岗位行/热招职位 → 职位详情抽屉；首页点公司名 → 公司详情（且不误触抽屉）；导航高亮正确 |
| 登录态渲染 | ✅ 导航出现「个人中心」，个人中心页含统计卡与 5 个子页签 |
| 路由守卫 | ✅ 未登录访问 `#/profile` 被弹回登录页 |
| 截图 | `web/screenshots/*.png`（home / login / companies / company_C1875D776 / resume / jobs / chat / profile） |

> **说明**：以上验证由脚本完成（`puppeteer-core` + 本机 Chrome），
> 目的是在**看不见画面的情况下**确认页面真的渲染、且无运行时报错。
> **配色与排版的美观程度仍需人工确认**。

> **踩坑记录（已修）**：有些工具用「临时目录 + 原子改名」写文件，Vite dev server 监听时会抛
> `EBUSY` 直接退出；`vite.config.ts` 已加 `server.watch.ignored` 忽略 `*.tmpdir` / `*.tmp`。

## 与 Streamlit 版的关系

| | Streamlit（`src/web/app.py`） | Vue3（`web/`） |
|---|---|---|
| 定位 | 保底交付 + 接口契约验证 | 答辩主秀 |
| 启动 | `streamlit run src/web/app.py` → 8501 | `npm run dev` → 5173 |
| 依赖 | 纯 Python | Node 工具链 |
| 自动化测试 | ✅ `tests/test_web.py`（AppTest 无头执行，10 项） | ⚠️ 暂无（已用无头渲染脚本临时验证） |
| 视觉上限 | 中 | 高 |

两套前端**调同一批接口**，因此数据与口径完全一致——这正是"前端只走 HTTP"的设计收益。
