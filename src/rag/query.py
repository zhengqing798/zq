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

    def structured_filter(self, city=None, keyword=None, salary_min=None, edu=None, k=5):
        """在原始岗位表上做精确规则筛选；→ (命中总数, 样例列表)"""
        def hit(r):
            if city and city not in (r["岗位地区"] or ""):
                return False
            if keyword:
                blob = ((r["岗位名称"] or "") + (r["技能标签"] or "") + (r["职位描述"] or "")).lower()
                if keyword.lower() not in blob:
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

        rows = [(i, r) for i, r in enumerate(self.jobs) if hit(r)]
        sample = [{"岗位ID": "J%04d" % (i + 1), "岗位名称": (r["岗位名称"] or "").strip(),
                   "城市": (r["岗位地区"] or "").split()[0] if (r["岗位地区"] or "").split() else "",
                   "薪资": r["岗位薪资"], "学历": r["学历要求"], "经验": r["经验要求"],
                   "公司": r["公司名称"]} for i, r in rows[:k]]
        return len(rows), sample

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
