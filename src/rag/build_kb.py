# -*- coding: utf-8 -*-
"""
任务10 · RAG 知识库构建（岗位数据 + 分析结论 → Embedding → 向量库）

三道工序：
  1. **卡片生成**：把结构化数据变成"可检索的知识卡"
     · 岗位卡（每岗位一张）：岗位名称｜公司｜城市｜薪资｜经验｜学历｜技能｜描述摘要
     · 结论卡（约 40 张）：从任务4/5/6/7 的报告里抽取关键结论（薪资分位、经验结构、学历门槛、
       技能热度、活跃雇主、城市分布、聚类画像 9+8 簇、评分模型指标、匹配权重口径）
  2. **向量化**：本地中文模型 `BAAI/bge-small-zh-v1.5`（512 维，[CLS] 向量 + L2 归一化），CPU 批量推理
  3. **入库**：Chroma 本地持久化集合（`data/rag/chroma/`），带 metadata（岗位ID/城市/薪资/类别/簇名）便于溯源

输出：
  · `data/rag/chroma/`                    向量库（持久化）
  · `data/processed/RAG_知识卡.csv`        全部卡片（含 ID/类型/文本/元数据），可审计
  · `data/processed/RAG_入库说明.md`       卡片构成、模型、耗时、检索自检

运行：python src/rag/build_kb.py [--limit N]   （--limit 用于先用少量岗位试跑）
"""
import argparse
import csv
import json
import os
import sys
import time

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "models", "scoring"))
from build_labels import load_csv                                              # noqa: E402

P = os.path.join(ROOT, "data", "processed")
RAG_DIR = os.path.join(ROOT, "data", "rag")
VEC_PATH = os.path.join(RAG_DIR, "jobs_kb_vectors.npy")
CARDS_META = os.path.join(RAG_DIR, "jobs_kb_cards.json")
JOBS_CSV = os.path.join(P, "zhaopin_jobs_cleaned_seg.csv")
OUT_CARDS = os.path.join(P, "RAG_知识卡.csv")
OUT_MD = os.path.join(P, "RAG_入库说明.md")
MODEL_NAME = "BAAI/bge-small-zh-v1.5"
BATCH = 64


# ---------------------------------------------------------------- 文本嵌入

class Embedder:
    """本地中文 embedding（BGE-small-zh-v1.5）：[CLS] 向量 + L2 归一化，余弦=点积"""

    def __init__(self, name=MODEL_NAME):
        import torch
        from transformers import AutoModel, AutoTokenizer
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(name)
        self.mdl = AutoModel.from_pretrained(name)
        self.mdl.eval()
        self.dim = self.mdl.config.hidden_size

    def encode(self, texts, batch=BATCH, progress=True):
        import numpy as np
        out = []
        t0 = time.time()
        for i in range(0, len(texts), batch):
            chunk = texts[i:i + batch]
            b = self.tok(chunk, padding=True, truncation=True, max_length=256, return_tensors="pt")
            with self.torch.no_grad():
                v = self.mdl(**b).last_hidden_state[:, 0]
            v = self.torch.nn.functional.normalize(v, p=2, dim=1)
            out.append(v.cpu().numpy())
            if progress and (i // batch) % 20 == 0:
                print("    已编码 %d/%d（%.0fs）" % (min(i + batch, len(texts)), len(texts), time.time() - t0), flush=True)
        return np.vstack(out).astype("float32")


# ---------------------------------------------------------------- 卡片生成

def job_card(r):
    parts = [
        "岗位：%s" % (r["岗位名称"] or "").strip(),
        "公司：%s" % (r["公司名称"] or "").strip(),
        "城市：%s" % ((r["岗位地区"] or "").split()[0] if (r["岗位地区"] or "").split() else ""),
        "薪资：%s（%s-%s 元/月）" % (r["岗位薪资"] or "", r["薪资下限(元/月)"] or "?", r["薪资上限(元/月)"] or "?"),
        "经验要求：%s" % (r["经验要求"] or "未标注"),
        "学历要求：%s" % (r["学历要求"] or "不限"),
        "技能标签：%s" % ("、".join(x.strip() for x in (r["技能标签"] or "").split("|") if x.strip()) or "无"),
        "职位描述摘要：%s" % (r["职位描述"] or "")[:160].replace("\n", " "),
    ]
    return "。".join(parts)


def conclusion_cards():
    """把任务4/5/6/7 的关键结论做成知识卡（数字均来自本项目报告，可溯源）"""
    C = []
    add = lambda t, txt, src: C.append({"类型": t, "文本": txt, "来源": src})
    add("薪资结论", "全部 8,833 条可解析薪资的岗位：月薪中位数 7,671 元，平均数 8,392 元，"
                    "P25-P75 区间 6,006-10,000 元，最小 1,000 元，最大 80,004 元；5-8 千是最大档（42.81%）。"
                    "描述市场行情应使用中位数而不是平均数（分布右偏）。", "可视化分析报告 图1/图11")
    add("薪资结论", "经验-薪资关系：1-3 年 7,752 元、3-5 年 8,834 元、5-10 年 9,941 元、10 年以上 12,579 元，"
                    "累计涨幅约 62%；苏州全程最高（10 年以上 15,705 元），福州起点最低（7,558 元）。", "可视化分析报告 图5")
    add("经验结论", "岗位经验要求集中在 1-5 年：3-5 年 2,708 条、1-3 年 2,441 条，合计 77.4%；10 年以上仅 117 条。", "可视化分析报告 图2")
    add("学历结论", "学历门槛：本科 55.75%、大专 34.25%（合计 90%），硕士 4.27%、中专/中技 2.93%、高中 2.21%、博士 0.59%。"
                    "大专简历可覆盖 42.2% 的岗位，本科可覆盖 95.4%。", "可视化分析报告 图4")
    add("技能结论", "岗位技能热度 Top：QE(390)、Python(349)、QC(327)、Java(318)、QA(280)、C++(269)、MySQL(228)、Spring(224)、"
                    "五险一金(213，属福利标签)、JavaScript(212)。数据源里混有大量制造业质量/检验岗位。", "可视化分析报告 图3")
    add("企业结论", "共 4,096 家企业；招聘最多的公司是软通动力（86 个岗位，仅占 0.97%）、三一集团（72）、外企德科（36）；"
                    "招聘集中度低（长尾），不能只靠少数大公司。", "可视化分析报告 图6")
    add("活跃度结论", "回复积极性：`回复时效` 字段 99.83% 为空，因此用 `今日回复数`（非空 52.3%）衡量；"
                      "在招岗位 ≥5 个的 360 家公司中最高分是厦门睿云联 84.7。必须区分「无回复数据」与「回复少」。", "可视化分析报告 图10")
    add("地域结论", "岗位仅覆盖 16 个城市、4 个省份：福建 3,553（40.21%）、浙江 2,656（30.06%）、江苏 2,073（23.46%）、"
                    "安徽 554（6.27%）；福建内部福州 1,173 与厦门 1,169 双核，宁德为 0。", "可视化分析报告 图8/图9")
    add("匹配结论", "人岗匹配分 = 0.38×技能 + 0.18×经验 + 0.12×学历 + 0.16×地域 + 0.10×薪资 + 0.06×专业证书（v2 权重，"
                    "用于在线推荐）；技能分 = 0.6×(0.7×岗位技能覆盖率+0.3×简历技能利用率) + 0.4×TF-IDF余弦。"
                    "v1 权重（0.30/0.20/0.15/0.15/0.12/0.08）是评分模型的标签口径。", "人岗匹配文档 第三节/第七节")
    add("匹配结论", "匹配打分性能：一份简历对全量 8,836 个岗位打分只需 0.17 秒；Top-10 推荐的岗位大类一致率 54.95%、"
                    "平均技能命中 3.11（v2 权重，200 份简历调优）。", "人岗匹配文档 第六节/第七节")
    add("评分模型结论", "评分模型：XGBoost 最优。主口径（测试集是未见过的简历）T1 回归 MAE 0.827（均值基线 8.711）、"
                        "T2 二分类 PR-AUC 0.965、NDCG@10 0.867；纯净标签上 MAE 0.370 说明特征足以还原规则。", "评分模型文档 第六节")
    add("评分模型结论", "仅用 3 个文本相似度特征时 T1 MAE 7.906、T2 PR-AUC 0.380（随机基线 0.181）："
                        "纯文本语义信号较弱，主要因为 500 份简历是合成数据、技能词与真实岗位重叠低。", "评分模型文档 第七节")
    add("聚类结论", "岗位聚类（K-Means）：定 K=9（轮廓系数 0.6735、ARI 1.0000）。"
                    "主要簇：软件测试 16.44%、后端开发 10.25%、运维/云与网络 8.37%、算法/人工智能 4.93%、前端 2.42%、"
                    "嵌入式/硬件 2.41%、产品/项目管理 2.16%、数据分析/BI 1.55%，另有 51.45% 的「其他」巨簇。", "岗位聚类说明")
    add("聚类结论", "聚类二阶细分（对 51.45% 的「其他」巨簇，K=8）：质量检验、供应链/物料/采购、硬件/仪器/自动化、"
                    "数据/统计分析、Java/后端、电子/半导体/设备、算法/AI 应用。"
                    "各簇薪资中位数差异明显：算法/AI 18,000 元、嵌入式 15,000 元、运维 8,000 元。", "岗位聚类说明 2.2 节")
    add("多模型对比结论", "评分模型与匹配规则的 Top-10 推荐重合度 0.788、Spearman 0.9909、NDCG@10 持平（0.7241 vs 0.7250）："
                          "模型是对规则的蒸馏；在线推荐用规则（0.17s 且无需特征工程），模型用于离线批量打分与口径校验。", "多模型对比分析报告 第二节")
    add("数据质量结论", "数据质量问题（已在《数据预处理文档》登记）：① `经验要求` 有 2,182 个岗位（24.69%）字段错位"
                        "（值为 JavaScript/QE 等），建模时按信息缺失给中性分；② `技能标签` 混入 247 个福利类与 511 个行业类标签，"
                        "计算技能匹配时已剔除；③ 简历侧 500 份为合成数据，居住地与期望城市 100% 一致。", "数据预处理文档 第四部分")
    return C


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(description="构建 RAG 知识库")
    ap.add_argument("--limit", type=int, default=0, help="只用前 N 个岗位试跑（0=全部）")
    ap.add_argument("--no-reset", action="store_true", help="不清空已有集合")
    a = ap.parse_args()

    jobs = load_csv(JOBS_CSV)
    if a.limit:
        jobs = jobs[:a.limit]
    print("岗位 %d 条 ｜ 生成知识卡…" % len(jobs))
    cards = []
    for i, r in enumerate(jobs):
        city = (r["岗位地区"] or "").split()
        cards.append({"id": "J%04d" % (i + 1), "类型": "岗位卡", "文本": job_card(r),
                      "岗位ID": "J%04d" % (i + 1), "岗位名称": (r["岗位名称"] or "").strip(),
                      "城市": city[0] if city else "", "薪资": r["岗位薪资"] or "",
                      "公司": r["公司名称"] or "", "来源": "zhaopin_jobs_cleaned_seg.csv"})
    for k, c in enumerate(conclusion_cards(), 1):
        cards.append({"id": "C%03d" % k, "类型": c["类型"], "文本": c["文本"],
                      "岗位ID": "", "岗位名称": c["类型"], "城市": "", "薪资": "", "公司": "", "来源": c["来源"]})
    print("卡片合计 %d 张（岗位卡 %d + 结论卡 %d）" % (len(cards), len(jobs), len(cards) - len(jobs)))

    emb = Embedder()
    import numpy as np
    cache = os.path.join(RAG_DIR, "embeddings_%d_%s.npy" % (len(cards), emb.dim))
    if os.path.exists(cache):
        vecs = np.load(cache)
        enc_sec = 0.0
        print("复用已缓存向量：%s" % os.path.relpath(cache, ROOT))
    else:
        print("模型 %s（%d 维）｜ 开始向量化…" % (MODEL_NAME, emb.dim))
        t0 = time.time()
        vecs = emb.encode([c["文本"] for c in cards])
        enc_sec = time.time() - t0
        os.makedirs(RAG_DIR, exist_ok=True)
        np.save(cache, vecs)
    print("向量矩阵：%s ｜ 向量化耗时 %.0fs（本次%s重算）" %
          (vecs.shape, enc_sec, "" if enc_sec else "未"))

    # ---------- 入库：向量落盘 + 卡片元数据（FAISS 内存索引在检索端重建） ----------
    # 说明：① 最初用 Chroma（pip 1.5.9）持久化，但**跨进程重新加载时报 "Error loading hnsw index"**；
    #       ② 改用同为课程候选的 FAISS 后，发现 **FAISS 的 C++ 层在 Windows 上无法打开中文路径**
    #          （本项目目录含中文），faiss.write_index 直接失败；
    #       ③ 最终方案：向量以 `.npy` 落盘（numpy 支持中文路径），**FAISS 索引在检索端加载时内存重建**
    #          （8,852 × 512 重建耗时 < 0.1s，代价可忽略）。检索距离用余弦（向量已 L2 归一化）。
    import numpy as np
    import faiss
    os.makedirs(RAG_DIR, exist_ok=True)
    vec_path = os.path.join(RAG_DIR, "jobs_kb_vectors.npy")
    np.save(vec_path, vecs)
    with open(CARDS_META, "w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False)
    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(vecs)
    print("入库完成：向量 %s（%s）+ 卡片 %d 张（%s）｜ FAISS 内存索引 %d 条" %
          (vecs.shape, os.path.relpath(vec_path, ROOT), len(cards), os.path.relpath(CARDS_META, ROOT), index.ntotal))

    with open(OUT_CARDS, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "类型", "文本", "岗位ID", "岗位名称", "城市", "薪资", "公司", "来源"])
        w.writeheader()
        w.writerows(cards)
    print("输出：%s" % os.path.relpath(OUT_CARDS, ROOT))

    # 检索自检（用 FAISS 索引复算）
    checks = [("厦门 Java 开发 3-5 年", 5), ("苏州 大专 质量工程师", 5), ("薪资 2 万以上的算法岗", 5),
              ("福州 前端 Vue", 5), ("经验不限 测试", 5)]
    lines = []
    for q, k in checks:
        qv = emb.encode([q], progress=False)
        D, I = index.search(qv, k)
        got = [(cards[j]["岗位名称"], cards[j]["城市"], round(float(s), 3)) for s, j in zip(D[0], I[0])]
        lines.append("  %-24s → %s" % (q, "；".join("%s(%s,%.2f)" % g for g in got)))
        print(lines[-1])
    write_md(cards, len(jobs), vecs.shape, enc_sec, lines)


def write_md(cards, n_jobs, shape, enc_sec, check_lines):
    L = ["# RAG 知识库入库说明（任务10 · 步骤1）\n",
         "| 项目 | 内容 |", "|------|------|",
         "| 向量库 | **FAISS**（`IndexFlatIP` + L2 归一化向量 = 余弦相似度）｜ 向量落盘 `data/rag/jobs_kb_vectors.npy`，"
         "**索引在检索端加载时内存重建**（8,852 × 512 重建 <0.1s） |",
         "| Embedding | **%s**（512 维，[CLS] 向量 + L2 归一化，CPU 推理；模型经 hf-mirror 下载） |" % MODEL_NAME,
         "| 卡片总数 | %d（岗位卡 %d + 结论卡 %d） |" % (len(cards), n_jobs, len(cards) - n_jobs),
         "| 向量矩阵 | %s ｜ 向量化耗时 %.0fs |" % (str(shape), enc_sec),
         "| 卡片明细 | `data/processed/RAG_知识卡.csv`（可逐条审计）｜ 元数据 `data/rag/jobs_kb_cards.json` |", "",
         "---", "",
         "## 一、卡片设计\n",
         "**岗位卡**（每岗位一张，共 %d 张）：把结构化字段拼成一句可读文本，字段顺序固定——\n" % n_jobs,
         "> `岗位：…。公司：…。城市：…。薪资：…（下限-上限 元/月）。经验要求：…。学历要求：…。技能标签：…。职位描述摘要：…（前 160 字）`\n",
         "**结论卡**（%d 张）：把任务4/5/6/7 的关键结论固化成知识卡，**每张都标注来源**（对应报告章节/图号），"
         "用于回答「薪资多少」「哪些技能最热」「聚类有几类」这类统计型问题——这类问题靠岗位卡检索效率低，"
         "直接命中结论卡更准。\n" % (len(cards) - n_jobs),
         "结论卡覆盖：薪资分位与经验-薪资曲线、经验结构、学历门槛、技能热度、企业集中度、招聘活跃度、"
         "地域分布、匹配权重与性能、评分模型指标、聚类画像（含二阶细分）、多模型对比、数据质量。\n",
         "## 二、检索自检\n"]
    L += ["```"] + check_lines + ["```", ""]
    L.append("## 三、为什么选 FAISS + 本地 BGE\n")
    L.append("| 选择 | 理由 |")
    L.append("|---|---|")
    L.append("| **FAISS** | ① 课程列出的候选向量库之一（Chroma/FAISS/Milvus）；② `IndexFlatIP` + 归一化向量即**精确余弦检索**，无需训练索引；③ 8,852 条规模下内存索引重建 <0.1s |")
    L.append("| **本地 BGE-small-zh-v1.5** | ① **DeepSeek 官方不提供 embedding 接口**，必须另找嵌入模型；② 中文效果好、模型约 95MB、512 维，CPU 可跑；③ 数据不出本机（岗位数据无需上传第三方） |")
    L.append("| 不用 Chroma | 先试 Chroma 1.5.9（本地持久化），**跨进程重新加载时报 `Error loading hnsw index`**，故换 FAISS |")
    L.append("| FAISS 索引不落盘 | **FAISS 的 C++ 层在 Windows 上无法打开中文路径**（本项目目录含中文），`faiss.write_index` 直接失败；因此向量用 `.npy` 落盘、索引启动时内存重建（代价 <0.1s） |")
    L.append("")
    L.append("## 四、局限与如实说明\n")
    L.append("| # | 说明 |")
    L.append("|---|---|")
    L.append("| 1 | 岗位卡把长职位描述截断到 160 字（控制向量质量与耗时），**长尾细节会丢**；如需精确匹配可在回答阶段回查原始 CSV |")
    L.append("| 2 | 结论卡是**人工整理**的报告结论，不是模型自动生成——好处是数字可溯源，坏处是覆盖面取决于整理者 |")
    L.append("| 3 | 检索是**纯语义**的（FAISS 无内建元数据过滤），城市/薪资等结构化条件由 `query.py` 的 `city` 过滤与 `structured_filter()` 补齐；召回评估对比了这两种模式 |")
    L.append("| 4 | 简历数据（500 份）**未入知识库**：本任务的问答场景是「岗位/市场」，简历侧用匹配工具处理更合适 |")
    L.append("")
    L.append("> 复现：`python src/rag/build_kb.py`（首次会从 hf-mirror 下载模型，约 95MB）")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
