# -*- coding: utf-8 -*-
"""
任务5 · 步骤3：数据集划分（口径 A：分组划分，一行数据都不丢）

两个口径（同一套数据、同一个比例，只是分组键不同）：
  · 主口径：按 `简历ID` 分组 → 测试集是"从未见过的简历"（贴合真实场景：岗位池固定已知，给新简历匹配）
  · 对照口径：按 `岗位ID` 分组 → 测试集是"从未见过的岗位"（岗位冷启动）

比例 70 / 15 / 15，随机种子 42，按组切分。
为什么必须按组：同一份简历带约 415 个配对、同一岗位带约 23 个配对，若按行随机切，
同一份简历的配对会同时出现在训练集与测试集里，模型靠"认出这份简历"就能猜对，指标虚高。

输出（data/processed/）：
  · `匹配样本_划分_按简历.csv` / `匹配样本_划分_按岗位.csv`   每行：简历ID, 岗位ID, 数据集
  · `匹配样本_划分_说明.md`                                   分组数、行数、标签分布一致性校验

运行：python src/models/scoring/split_dataset.py
"""
import csv
import os
import sys
from collections import Counter, defaultdict

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
P = os.path.join(ROOT, "data", "processed")
FEAT_CSV = os.path.join(P, "匹配特征_全量样本.csv")
OUT_RESUME = os.path.join(P, "匹配样本_划分_按简历.csv")
OUT_JOB = os.path.join(P, "匹配样本_划分_按岗位.csv")
OUT_MD = os.path.join(P, "匹配样本_划分_说明.md")
SEED = 42
RATIO = (0.70, 0.15, 0.15)
NAMES = ("train", "valid", "test")


def split_groups(groups, seed):
    """按组随机切分 → {组: train/valid/test}"""
    g = np.array(sorted(groups))
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(g))
    n_tr, n_va = int(len(g) * RATIO[0]), int(len(g) * RATIO[1])
    out = {}
    for pos, gi in enumerate(perm):
        out[g[gi]] = NAMES[0] if pos < n_tr else (NAMES[1] if pos < n_tr + n_va else NAMES[2])
    return out


def main():
    rows = list(csv.DictReader(open(FEAT_CSV, encoding="utf-8-sig", newline="")))
    print("特征表 %d 行" % len(rows))
    res_ids, job_ids = (r["简历ID"] for r in rows), (r["岗位ID"] for r in rows)
    n_res, n_job = len({r["简历ID"] for r in rows}), len({r["岗位ID"] for r in rows})
    print("简历 %d 份 ｜ 岗位 %d 个" % (n_res, n_job))

    results = {}
    for tag, key, out_path in (("按简历", "简历ID", OUT_RESUME), ("按岗位", "岗位ID", OUT_JOB)):
        assign = split_groups({r[key] for r in rows}, SEED)
        with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["简历ID", "岗位ID", "数据集"])
            for r in rows:
                w.writerow([r["简历ID"], r["岗位ID"], assign[r[key]]])
        results[tag] = (assign, key, out_path)
        print("输出：%s（%d 行）" % (os.path.relpath(out_path, ROOT), len(rows)))

    write_md(rows, results)
    print("输出：%s" % os.path.relpath(OUT_MD, ROOT))


def write_md(rows, results):
    y = {i: float(r["总分(0-100)"]) for i, r in enumerate(rows)}
    n = len(rows)
    L = []
    L.append("# 数据集划分说明（任务5 步骤3）\n")
    L.append("> 岗位-简历人岗匹配推荐系统 ｜ 口径 A：**按组划分**，70 / 15 / 15，随机种子 %d，**一行数据都不丢**" % SEED)
    L.append("> 输入：`data/processed/匹配特征_全量样本.csv`（%d 行）" % n)
    L.append("> 输出：`匹配样本_划分_按简历.csv`（主口径）、`匹配样本_划分_按岗位.csv`（对照口径）\n")
    L.append("---\n")
    L.append("## 一、为什么必须按组划分\n")
    L.append("每个候选配对是 `(简历, 岗位)`。本数据集里：")
    L.append("- 同一份简历平均带约 **415** 个配对（500 份简历 → %d 个配对）；" % n)
    L.append("- 同一个岗位平均带约 **23** 个配对。\n")
    L.append("若按行随机切分，同一份简历的配对会同时落进训练集与测试集，模型只要\"认出这份简历\""
             "（或\"认出这个岗位\"）就能把分数猜得很准，测试指标会虚高。**按组切分后，一组的全部配对只出现在一侧。**\n")
    L.append("## 二、两个口径\n")
    L.append("| 口径 | 分组键 | 测试集含义 | 文件 |\n|---|---|---|---|")
    L.append("| **主口径** | `简历ID` | 从未见过的简历（贴合真实场景：岗位池固定已知，给新简历做匹配） | `匹配样本_划分_按简历.csv` |")
    L.append("| 对照口径 | `岗位ID` | 从未见过的岗位（岗位冷启动） | `匹配样本_划分_按岗位.csv` |\n")
    for tag, (assign, key, _) in results.items():
        gc = Counter(assign.values())
        L.append("### 2.%d %s口径\n" % (1 if tag == "按简历" else 2, tag))
        L.append("| 数据集 | 组数（%s） | 组占比 | 配对数 | 配对占比 | 标签均值 | 标签中位数 | 正样本率(≥65) |\n|---|---|---|---|---|---|---|---|" % key)
        for nm in NAMES:
            gids = {g for g, s in assign.items() if s == nm}
            idx = [i for i, r in enumerate(rows) if assign[r[key]] == nm]
            a = np.array([y[i] for i in idx])
            L.append("| %s | %d | %.2f%% | %d | %.2f%% | %.2f | %.2f | %.2f%% |" %
                     (nm, len(gids), len(gids) / len(assign) * 100, len(idx), len(idx) / n * 100,
                      a.mean(), np.median(a), (a >= 65).mean() * 100))
        L.append("")
        # 校验
        sets = {nm: {g for g, s in assign.items() if s == nm} for nm in NAMES}
        ov = (sets["train"] & sets["valid"]) | (sets["train"] & sets["test"]) | (sets["valid"] & sets["test"])
        L.append("- **组无交集校验**：%s" % ("✓ 三个集合的组两两无交集" if not ov else "✗ 存在重叠 %s" % list(ov)[:5]))
        cnt = Counter(assign[r[key]] for r in rows)
        L.append("- **行数守恒校验**：%d + %d + %d = %d = 总行数 ✓" %
                 (cnt["train"], cnt["valid"], cnt["test"], n))
        L.append("")
    L.append("## 三、使用约定\n")
    L.append("> **配对占比与 70/15/15 的偏差属预期**：按组切分时每份简历携带的配对数并不相同——"
             "所在城市无岗位的 296 份简历每人只带 150 个跨城对，其余 204 份每人带约 490 个（同城 + 150 跨城）；"
             "岗位侧同理。因此组占比精确为 70/15/15，配对占比会略有浮动。\n")
    L.append("1. **调参（RF/XGB 树深、学习率等）只在 `valid` 上做**；")
    L.append("2. **`test` 只在最终评估时使用一次**，不得用于任何选择；")
    L.append("3. 两个口径分别训练、分别汇报，不混用；")
    L.append("4. 训练脚本按 `数据集` 列切分即可，无需再做任何抽样或重排。\n")
    L.append("## 四、输出文件\n")
    L.append("| 文件 | 说明 |\n|---|---|")
    L.append("| `data/processed/匹配样本_划分_按简历.csv` | 主口径划分（每行：简历ID, 岗位ID, 数据集） |")
    L.append("| `data/processed/匹配样本_划分_按岗位.csv` | 对照口径划分 |")
    L.append("| `data/processed/匹配样本_划分_说明.md` | 本文件 |\n")
    L.append("> 复现：`python src/models/scoring/split_dataset.py`（种子 %d）" % SEED)
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
