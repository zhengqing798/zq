# -*- coding: utf-8 -*-
"""
任务10 · RAG 检索模块（被召回评估与 Agent 工具共用）

提供：
  · `Retriever.search(query, k, only_jobs=False, city=None)` —— 语义检索（FAISS + 本地 BGE）
  · `Retriever.structured_filter(...)` —— 结构化筛选（直接在清洗后的岗位表上做规则过滤）
  · `Retriever.salary_stats(city=None)` —— 薪资统计
  · `Retriever.cluster_profile(name)` —— 任务7 聚类画像查询
  · `get_retriever()` —— 进程内单例（模型与索引只加载一次）

设计说明：
  · 向量检索是**纯语义**的；"厦门 + Java"这类带硬条件的问句，纯语义可能召回其他城市的同类岗位，
    因此 `search()` 支持可选 `city` 过滤（FAISS 无元数据过滤，这里取回全部再过滤，8,852 条代价可忽略）。
  · 数值条件（"月薪 2 万以上"）走 `structured_filter()`（精确规则），不交给向量检索。
"""
import json
import os
import re
import sys

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "models", "scoring"))
from build_labels import load_csv                                     # noqa: E402
from build_kb import Embedder, VEC_PATH, CARDS_META, JOBS_CSV, MODEL_NAME   # noqa: E402

_R = None

# ---------------------------------------------------------------- 关键词匹配
# 背景（2026-09-15 修复）：原先 filter_jobs 的关键词是**整串子串匹配**
# （`keyword.lower() not in blob`）。LLM 常把关键词写成组合短语（如「Java 开发工程师」），
# 于是「Java工程师」「java」「Java后端开发」全都检索不到——同一类岗位召回率极低。
# 现在改为：归一化 → 切分 → 去掉无区分度的泛词 → **按核心词 OR 匹配**，
# 且 ASCII 核心词加词边界（避免 java 命中 javascript）。

# 泛词：只表示「岗位/工作」这类无区分度的词，作为**独立片段**出现时不参与匹配
GENERIC_TERMS = {
    "开发", "工程师", "岗位", "职位", "工作", "招聘", "相关", "技术", "人员", "若干", "名",
    "高级", "中级", "初级", "资深", "专家", "助理", "实习", "全职", "兼职", "急招", "优先",
    "developer", "developers", "engineer", "engineers", "job", "jobs", "position",
    "senior", "junior", "staff",
}

_FULL2HALF = str.maketrans("＋＃（）．－／　", "+#().-/ ")
_SEP = "、，,;；|｜/\\()（）[]【】·•:：\"'"
_TOKEN_RE = re.compile(r"[a-z0-9+#.]+|[\u4e00-\u9fff]+")
_ASCII_TERM = re.compile(r"^[a-z0-9+#.]+$")
# 中文泛词按长度降序，供「剥离式」判定使用（"开发工程师" = 开发+工程师 → 无区分度）
_GENERIC_CJK = sorted([w for w in GENERIC_TERMS if not _ASCII_TERM.match(w)], key=len, reverse=True)


def strip_generic_cjk(tok):
    """把中文片段里的泛词**剥掉**，返回有区分度的剩余部分（可能为空串）。

    「开发工程师」→ ''（纯泛词）｜「后端开发」→ '后端'｜「高级前端」→ '前端'｜「软件测试」→ '软件测试'
    """
    out = tok
    changed = True
    while changed:
        changed = False
        for g in _GENERIC_CJK:
            if g and g in out:
                out = out.replace(g, "")
                changed = True
    return out


def normalize_text(s):
    """小写 + 全角转半角 + 各类分隔符统一为空格"""
    s = (s or "").translate(_FULL2HALF).lower()
    for ch in _SEP:
        s = s.replace(ch, " ")
    return re.sub(r"\s+", " ", s).strip()


def keyword_terms(keyword):
    """把关键词拆成「核心词」列表（剔除泛词）。

    「Java」            → ['java']
    「Java 开发工程师」 → ['java']      （开发工程师 是纯泛词组合，整体剔除）
    「Java开发」        → ['java']      （中英混排按字符类型切开）
    「后端开发」        → ['后端']       （剥掉泛词"开发"）
    「软件测试」        → ['软件测试']   （无泛词，整体保留）
    「开发」            → ['开发']       （全是泛词时退回原词，避免匹配到空）
    """
    norm = normalize_text(keyword)
    if not norm:
        return []
    terms = []
    for tok in norm.split(" "):
        parts = [p for p in _TOKEN_RE.findall(tok) if p]
        if len(parts) <= 1:
            parts = [tok]
        for p in parts:
            if _ASCII_TERM.match(p):
                if p in GENERIC_TERMS:
                    continue
                cand = p
            else:
                cand = strip_generic_cjk(p)      # 剥掉中文泛词
                if not cand:
                    continue                     # 剥完为空 → 该片段无区分度
            if cand not in terms:
                terms.append(cand)
    return terms or [norm]


def term_hit(term, blob):
    """单个核心词是否命中（blob 为已归一化文本）"""
    if _ASCII_TERM.match(term):
        # 词边界：java 命中「java开发」，但不命中「javascript」
        pat = r"(?<![a-z0-9+#])" + re.escape(term) + r"(?![a-z0-9+#])"
        return re.search(pat, blob) is not None
    # 中文词：忽略空格后再找（"软件 测试" 也能命中"软件测试"）
    return term in blob.replace(" ", "")


STAT_Q = ("中位数", "平均", "多少", "几类", "几个", "占比", "比例", "最高", "最低", "排名", "分布",
          "统计", "分成", "几档", "几成", "涨幅", "区间", "门槛", "总体", "整体", "市场", "最热", "哪个")


class Retriever:
    def __init__(self):
        import faiss
        import numpy as np
        self.emb = Embedder(MODEL_NAME)
        self.vecs = np.load(VEC_PATH)                  # 向量以 .npy 落盘（FAISS 无法处理中文路径）
        self.cards = json.load(open(CARDS_META, encoding="utf-8"))
        self.jobs = load_csv(JOBS_CSV)
        self.cities = sorted({(r["岗位地区"] or "").split()[0] for r in self.jobs if (r["岗位地区"] or "").split()})
        # 两个索引：岗位卡 + 结论卡（分类型检索，避免 16 张结论卡被 8,836 张岗位卡淹没）
        self.job_pos = [i for i, c in enumerate(self.cards) if c["类型"] == "岗位卡"]
        self.conc_pos = [i for i, c in enumerate(self.cards) if c["类型"] != "岗位卡"]
        self.index_jobs = faiss.IndexFlatIP(self.vecs.shape[1])
        self.index_jobs.add(self.vecs[self.job_pos])   # 启动时内存重建索引，<0.1s
        self.index_conc = faiss.IndexFlatIP(self.vecs.shape[1])
        self.index_conc.add(self.vecs[self.conc_pos])

    @staticmethod
    def route(query):
        """问句路由：统计/结论型 → 先查结论卡；否则查岗位卡"""
        return "conclusions" if any(q in query for q in STAT_Q) else "jobs"

    def _q(self, index, pos, query, k, city=None):
        qv = self.emb.encode([query], progress=False)
        D, I = index.search(qv, min(len(pos), max(k * 4, k)))
        out = []
        for score, j in zip(D[0], I[0]):
            if j < 0:
                continue
            c = self.cards[pos[j]]
            if city and c["城市"] != city:
                continue
            out.append({**c, "score": round(float(score), 4)})
            if len(out) >= k:
                break
        return out

    def search(self, query, k=5, only_jobs=False, city=None, mode="auto", fallback=True):
        """mode: auto（按问句路由）｜jobs（只看岗位卡）｜conclusions（只看结论卡）｜all（全库）"""
        m = self.route(query) if mode == "auto" else mode
        if only_jobs or m == "jobs":
            return self._q(self.index_jobs, self.job_pos, query, k, city)
        out = self._q(self.index_conc, self.conc_pos, query, k, city)
        if m == "conclusions":
            if fallback and len(out) < k:
                out += self._q(self.index_jobs, self.job_pos, query, k - len(out), city)
            return out
        # all：结论卡优先，不足用岗位卡补齐
        if len(out) < k:
            out += self._q(self.index_jobs, self.job_pos, query, k - len(out), city)
        return out

    def _blobs(self):
        """每个岗位的归一化匹配文本（懒加载 + 进程内缓存，避免每次筛选重复归一化）"""
        if not hasattr(self, "_blob_cache"):
            self._blob_cache = []
            for r in self.jobs:
                self._blob_cache.append((
                    normalize_text(r["岗位名称"]),
                    normalize_text(r["技能标签"]),
                    normalize_text(r["职位描述"]),
                ))
        return self._blob_cache

    def structured_filter(self, city=None, keyword=None, salary_min=None, edu=None, k=5):
        """在原始岗位表上做规则筛选。

        keyword 采用**核心词匹配**（见模块头部说明），并返回**分层命中数**：
          · 岗位名称命中（严格）
          · 名称或技能标签命中（**主口径**，作为返回的命中总数）
          · 名称/技能标签/职位描述任一命中（宽口径，仅作参考）
        返回值：(主口径命中数, 样例列表, 分层统计 dict)；样例优先给"名称或技能标签命中"的岗位。
        """
        terms = keyword_terms(keyword) if keyword else []

        def base_ok(r):
            if city and city not in (r["岗位地区"] or ""):
                return False
            if salary_min is not None:
                try:
                    if int(r["薪资下限(元/月)"] or 0) < int(salary_min):
                        return False
                except ValueError:
                    return False
            if edu and edu not in (r["学历要求"] or ""):
                return False
            return True

        blobs = self._blobs()
        multi = len(terms) > 1
        rows, tiers = [], {"岗位名称": 0, "名称或技能标签": 0, "全字段": 0}
        if multi:
            tiers["任一核心词_名称或技能标签"] = 0
        for i, r in enumerate(self.jobs):
            if not base_ok(r):
                continue
            if terms:
                b_name, b_skill, b_desc = blobs[i]
                # 主口径：**所有**核心词都要命中（多核心词按 AND，避免"Java 后端"把纯后端岗也算进来）
                h_name = all(term_hit(t, b_name) for t in terms)
                h_skill = all(term_hit(t, b_skill) for t in terms)
                h_tight = h_name or h_skill
                h_field = h_tight or all(term_hit(t, b_desc) for t in terms)
                if multi and any(term_hit(t, b_name) or term_hit(t, b_skill) for t in terms):
                    tiers["任一核心词_名称或技能标签"] += 1   # 宽口径（任一核心词命中）
                if not h_field:
                    continue
                tiers["岗位名称"] += 1 if h_name else 0
                tiers["名称或技能标签"] += 1 if h_tight else 0
                tiers["全字段"] += 1
                rows.append((i, r, h_tight))
            else:
                tiers["岗位名称"] += 1
                tiers["名称或技能标签"] += 1
                tiers["全字段"] += 1
                rows.append((i, r, True))

        # 样例优先给严格命中的（岗位名称/技能标签），再补宽口径的
        rows.sort(key=lambda x: (not x[2],))
        sample = [{"岗位ID": "J%04d" % (i + 1), "岗位名称": (r["岗位名称"] or "").strip(),
                   "城市": (r["岗位地区"] or "").split()[0] if (r["岗位地区"] or "").split() else "",
                   "薪资": r["岗位薪资"], "学历": r["学历要求"], "经验": r["经验要求"],
                   "技能标签": (r["技能标签"] or "")[:60], "公司": r["公司名称"]}
                  for i, r, _ in rows[:k]]
        # 主口径：名称或技能标签命中（"描述里提了一句"不算，避免把无关岗位算成该类岗位）
        return tiers["名称或技能标签"], sample, tiers

    def salary_stats(self, city=None):
        import numpy as np
        pairs = []
        for r in self.jobs:
            if city and city not in (r["岗位地区"] or ""):
                continue
            try:
                lo, hi = int(r["薪资下限(元/月)"] or 0), int(r["薪资上限(元/月)"] or 0)
            except ValueError:
                continue
            if lo > 0 and hi > 0:
                pairs.append((lo, hi))
        if not pairs:
            return None
        mids = sorted((a + b) / 2 for a, b in pairs)
        return {"城市": city or "全部岗位", "样本数": len(pairs),
                "下限中位数": int(np.median([a for a, _ in pairs])),
                "上限中位数": int(np.median([b for _, b in pairs])),
                "区间中点中位数": int(np.median(mids)),
                "P25(下限)": int(np.percentile([a for a, _ in pairs], 25)),
                "P75(上限)": int(np.percentile([b for _, b in pairs], 75)),
                "最大上限": max(b for _, b in pairs)}

    def cluster_profile(self, name=None):
        """任务7 聚类画像（按簇名/方案关键词匹配）"""
        path = os.path.join(ROOT, "data", "processed", "岗位聚类_簇画像.csv")
        if not os.path.exists(path):
            return []
        rows = load_csv(path)
        key = (name or "").strip()
        return [r for r in rows if not key or key in r["簇名"] or key in r["方案"]][:8]


def get_retriever():
    global _R
    if _R is None:
        _R = Retriever()
    return _R
