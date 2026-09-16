#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""环境体检：从 GitHub 克隆下来后，先跑这个，它会告诉你缺什么、怎么补。

用法：
    python scripts/doctor.py            # 体检并给出后续命令
    python scripts/doctor.py --brief    # 只看结论

为什么要这个脚本：
    仓库只提交**源码 + 根数据 + 文档**（约 105 MB），另外 5 个体积大但**可一键重建**的
    派生产物（配对标签 27MB、特征表 26MB、RAG 向量与卡片 43MB）没有入库。
    本脚本按「必须入库的 / 可重建的 / 需外部下载的」三类逐项检查，缺什么就给什么命令。
"""
import argparse
import importlib
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.chdir(ROOT)

OK, BAD, WARN, INFO = "✅", "❌", "⚠️ ", "  "

# ---------------------------------------------------------------- 检查清单
# 第三方包：import 名 → pip 安装名
PACKAGES = [
    ("numpy", "numpy"), ("pandas", "pandas"), ("sklearn", "scikit-learn"),
    ("xgboost", "xgboost"), ("matplotlib", "matplotlib"), ("jieba", "jieba"),
    ("requests", "requests"), ("faiss", "faiss-cpu"), ("torch", "torch"),
    ("transformers", "transformers"), ("pdfplumber", "pdfplumber"),
    ("reportlab", "reportlab"), ("joblib", "joblib"), ("scipy", "scipy"),
    ("openpyxl", "openpyxl"),
]

# 必须入库的（克隆后就应该在）
REQUIRED = [
    ("data/processed/zhaopin_jobs_cleaned_seg.csv", "岗位分词表 8,836 行（全系统根数据）"),
    ("data/processed/简历数据_cleaned.csv", "简历结构化 500 份"),
    ("data/processed/简历数据_seg.csv", "简历分词表 500 份"),
    ("data/processed/技能同义词表.csv", "技能归一映射（标签/匹配共用）"),
    ("data/processed/技能词典_匹配用.csv", "技能词典 3,975 词"),
    ("data/processed/匹配样本_划分_按简历.csv", "任务5 划分（主口径）"),
    ("data/processed/匹配样本_划分_按岗位.csv", "任务5 划分（对照口径）"),
    ("models/模型元数据.json", "上线模型元信息"),
    ("data/raw/zhaopin_jobs_full.csv", "任务2 爬取原始数据"),
]

# 可一键重建的：路径 → (说明, 生成命令, 依赖的上游)
REGEN = [
    ("data/processed/匹配样本_标签数据.csv", "配对标签 207,640 行（27 MB）",
     "python src/models/scoring/build_labels.py", "根数据"),
    ("data/processed/匹配特征_全量样本.csv", "配对特征 207,640 行（26 MB）",
     "python src/models/scoring/build_features.py", "上一步的标签文件"),
    ("data/rag/jobs_kb_cards.json", "RAG 卡片元数据（8 MB）",
     "python src/rag/build_kb.py", "根数据 + BGE 模型"),
    ("data/rag/jobs_kb_vectors.npy", "RAG 向量矩阵 8,852×512（17 MB）",
     "python src/rag/build_kb.py", "同上"),
    ("data/rag/embeddings_8852_512.npy", "向量缓存（17 MB，可省）",
     "python src/rag/build_kb.py", "同上"),
]

# 需外部下载的
HF_MODEL = "models--BAAI--bge-small-zh-v1.5"
MODELS = [
    "models/按简历_T1回归_best_XGBoost.joblib",
    "models/按岗位_T1回归_best_XGBoost.joblib",
    "models/按简历_T2分类_best_XGBoost.joblib",
    "models/按岗位_T2分类_best_XGBoost.joblib",
]


def human(n):
    return "%.1f MB" % (n / 1048576.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brief", action="store_true", help="只输出结论")
    a = ap.parse_args()

    problems, commands = [], []

    print("=" * 74)
    print("岗位-简历人岗匹配推荐系统 · 环境体检")
    print("仓库根目录：%s" % ROOT)
    print("=" * 74)

    # ---------- 1. Python ----------
    v = sys.version_info
    ok_py = v >= (3, 10)
    print("\n【1】Python 版本")
    print("   %s Python %d.%d.%d（要求 ≥3.10）" % (OK if ok_py else BAD, v.major, v.minor, v.micro))
    if not ok_py:
        problems.append("Python 版本过低")
        print("       %s推荐装 Python 3.12" % INFO)

    # ---------- 2. 依赖包 ----------
    print("\n【2】第三方依赖")
    missing_pip = []
    for mod, pip in PACKAGES:
        try:
            m = importlib.import_module(mod)
            ver = getattr(m, "__version__", "?")
            print("   %s %-14s %s" % (OK, mod, ver))
        except Exception as e:
            print("   %s %-14s 缺失（%s）" % (BAD, mod, type(e).__name__))
            missing_pip.append(pip)
    if missing_pip:
        problems.append("缺少 %d 个依赖包" % len(missing_pip))
        commands.append("pip install " + " ".join(sorted(set(missing_pip))))
        print("\n       %s装法：pip install %s" % (INFO, " ".join(sorted(set(missing_pip)))))

    # ---------- 3. .env ----------
    print("\n【3】大模型密钥（.env）")
    env = {}
    if os.path.exists(".env"):
        for line in open(".env", encoding="utf-8", errors="replace"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, val = line.split("=", 1)
                env[k.strip()] = val.strip()
    for key in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"):
        if env.get(key):
            print("   %s %s = %s" % (OK, key, "***（已设置）" if "KEY" in key else env[key]))
        else:
            print("   %s %s 未设置" % (BAD, key))
            problems.append("缺少 .env 的 %s" % key)
    if not env.get("DEEPSEEK_API_KEY"):
        print("       %s建一个 .env（**不要提交**，已在 .gitignore 里）：" % INFO)
        print("          DEEPSEEK_API_KEY=sk-你的key")
        print("          DEEPSEEK_BASE_URL=https://api.deepseek.com")
        print("          DEEPSEEK_MODEL=deepseek-chat")

    # ---------- 4. 必须入库的文件 ----------
    print("\n【4】根数据与模型（克隆后应当已存在）")
    for path, desc in REQUIRED:
        if os.path.exists(path):
            print("   %s %-46s %s" % (OK, path, human(os.path.getsize(path))))
        else:
            print("   %s %-46s 缺失！%s" % (BAD, path, desc))
            problems.append("缺根数据 %s" % path)
    for path in MODELS:
        if os.path.exists(path):
            print("   %s %-46s %s" % (OK, path, human(os.path.getsize(path))))
        else:
            print("   %s %-46s 缺失！（跑 train_models.py 可重建）" % (WARN, path))
            problems.append("缺模型 %s" % path)

    # ---------- 5. 可重建的派生产物 ----------
    print("\n【5】大体积派生产物（未入库，可一键重建）")
    need_build = []
    for path, desc, cmd, dep in REGEN:
        if os.path.exists(path):
            print("   %s %-46s %s" % (OK, path, human(os.path.getsize(path))))
        else:
            print("   %s %-46s 缺失 → %s" % (WARN, path, cmd))
            if cmd not in need_build:
                need_build.append(cmd)
    if need_build:
        print("\n       %s按顺序执行（约 3~8 分钟）：" % INFO)
        for i, c in enumerate(need_build, 1):
            print("          %d) %s" % (i, c))
        commands.extend(need_build)

    # ---------- 6. Embedding 模型 ----------
    print("\n【6】本地 Embedding 模型（BGE，约 92 MB，不在仓库里）")
    hf = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub", HF_MODEL)
    if os.path.isdir(hf):
        size = sum(os.path.getsize(os.path.join(r, f))
                   for r, d, fs in os.walk(hf) for f in fs)
        print("   %s 已缓存：%s（%s）" % (OK, hf.replace(os.path.expanduser("~"), "~"), human(size)))
    else:
        print("   %s 未缓存 —— 首次跑 build_kb.py 时会自动从 hf-mirror.com 下载（约 92 MB）" % WARN)
        print("       %s国内网络已内置镜像：HF_ENDPOINT=https://hf-mirror.com" % INFO)

    # ---------- 结论 ----------
    print("\n" + "=" * 74)
    if not problems:
        print("✅ 体检通过：环境和数据齐备，可以直接跑。")
    else:
        print("⚠️  发现 %d 类问题，按下面顺序处理：" % len(problems))
        for i, p in enumerate(dict.fromkeys(problems), 1):
            print("   %d. %s" % (i, p))
        if commands:
            print("\n   修复命令（按顺序）：")
            for c in dict.fromkeys(commands):
                print("     %s" % c)
    print("=" * 74)

    if not a.brief:
        print("""
接着就能跑（任选）：

  # 1) Agent 智能问答（需 .env 里的 Key）
  python src/agent/agent.py --ask "福州市的Java岗位有多少个？"
  python src/agent/agent.py --repl

  # 2) 人岗匹配（贴简历，返回 Top-N + 六维分 + 推荐理由）
  python src/models/matching/match.py --text "大专 3 年软件测试 Selenium JMeter Python MySQL 期望苏州" --top 5

  # 3) RAG 召回评估 / 问答三元组
  python src/rag/evaluate_recall.py
  python src/rag/make_triples.py

  # 4) 复现任务5/7/8 的模型与报告
  python src/models/scoring/train_models.py
  python src/models/clustering/kmeans_jobs.py
  python src/models/comparison/compare_models.py
""")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
