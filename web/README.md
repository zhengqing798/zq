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
    │   ├── home.ts         # 首页推荐类型（/api/home）
    │   ├── companies.ts    # 公司浏览类型（公司页）
    │   └── index.ts        # 34 个接口的封装
    ├── stores/
    │   ├── auth.ts         # 登录态（令牌存 localStorage）
    │   └── resume.ts       # 跨页共享的"本次简历"
    ├── router/index.ts     # 路由 + 登录守卫（岗位推荐 / 个人中心需登录）
    ├── layouts/AppLayout.vue   # 顶部吸顶导航（首页/岗位/公司，登录后+岗位推荐）+ 用户下拉
    ├── components/
    │   ├── EChart.vue          # ECharts 轻量封装
    │   ├── CompanyCard.vue     # 公司卡（公司列表 + 详情页「相似公司」共用）
    │   └── JobDetailDrawer.vue # ★ 职位详情抽屉（首页/岗位/公司页/公司详情共用）
    └── views/
        ├── LoginView.vue       # 登录/注册：整页浅青渐变 + **居中卡片**（420px）；注册仅 3 个字段（无角色选择）
        ├── HomeView.vue        # ★ 首页推荐：热门分类 hero 轮播 + 地区推荐 + 高薪岗位 + 热门岗位 + 热门企业 + 热门技能
        ├── JobsBrowseView.vue  # ★ 岗位：仿 BOSS直聘 浏览筛选（支持 ?city= / ?source_kw= / ?keyword= / ?sort=）
        ├── MatchView.vue       # ★ 岗位推荐（需登录）：用简历做六维加权匹配
        ├── CompaniesView.vue   # ★ 公司广场：热门/最活跃企业榜 + 筛选 + 公司卡网格
        ├── CompanyView.vue     # ★ 公司详情：全部在招岗位 + 公司画像 + 招聘者 + 相似公司
        ├── ChatView.vue        # 对话 + 工具轨迹时间线 + 来源（保留页面，**当前无导航入口**）
        └── ProfileView.vue     # 个人中心（4 个子页签：我的简历（含粘贴/PDF 上传）/ 收藏 / 匹配历史 / 账号设置）
```

> **导航与入口约定（2026-09-18 改版）**：
> 顶部标签只有 **首页 ｜ 岗位 ｜ 公司**（游客可见），登录后追加 **岗位推荐**；**个人中心只从右上角用户下拉进入**（无标签）；
> **简历没有独立页面**——粘贴正文 / 上传 PDF / 解析 / 保存都在个人中心的「我的简历」页签里，解析完一键去「岗位推荐」；
> 旧地址 `#/resume` 自动重定向到个人中心。**智能问答页面与后端保留**，只是当前没有导航入口（`#/chat` 仍可访问）。
> 已删除的页面：`ClustersView.vue`（岗位聚类，2026-09-18）、`ResumeView.vue`（并入个人中心）、`JobsView.vue`（改名为 `MatchView.vue` 并挂到 `/match`）。

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
| `npm run build` | ✅ 成功（~0.7s，产物 dist/） |
| 后端接口 | ✅ **176 项 pytest 全绿**（新增 `tests/test_home.py` 21 项：首页推荐榜单口径/跨接口一致性/诚实性/边界/异常） |
| **无头真实渲染**（本机 Chrome headless，**8 个路由 + 2 个旧地址 + 游客态**） | ✅ 全部通过，**控制台 0 error**；反向断言扫描**全量 DOM 文本**（含隐藏页签），`🏢 岗位聚类` / `口径说明` / `职位分类导航面板` / `职位推荐` / `问答记录` / 已删文案一旦回流即报错 |
| **游客态**（独立无痕上下文） | ✅ 游客导航只有「首页 ｜ 岗位 ｜ 公司」；`#/match`、`#/profile` 均被弹回登录页 |
| **旧地址重定向** | ✅ `#/resume` → 个人中心（简历输入可见）；已删除的 `#/clusters` → 兜底回首页 |
| **首页真实点击** | ✅ hero 轮播 8 屏且自动滚动；点分类 → `?source_kw=` 精确落地 **2,564** 条；点地区卡 → `?city=苏州` 落地 **2,073** 条；点示例岗位 → 职位详情抽屉；点企业卡 → 公司详情 |
| **个人中心简历链路** | ✅ 页签只剩 4 个（无问答记录）；粘贴示例 → 解析成功 → 保存入库（表格 0 → 1 行）→ 一键去岗位推荐 |
| **登录页布局几何**（量测 1440/1920/420 视口） | ✅ 卡片与品牌头水平居中（误差 ≤2px）、宽度收敛 420px（窄屏自适应 392px）、无横向滚动条 |
| 截图 | `web/screenshots/*.png`（home / login / jobs / match / companies / company_C1875D776 / profile / chat） |

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
