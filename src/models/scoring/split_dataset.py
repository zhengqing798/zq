# -*- coding: utf-8 -*-
"""
任务5 · 数据集划分落盘：把全量样本按与训练脚本完全相同的规则切成三个文件

规则（与 train_models.py 完全一致，固定随机种子 42，保证可复现）：
  ① 严格划分：简历与岗位都不重叠
     - 训练集 = 训练简历 × 训练岗位
     - 测试集 = 测试简历 × 测试岗位
     - 两侧交叉的配对丢弃（否则模型会"背下"简历/岗位个体特征造成泄漏）
  ② 再从训练集里按简历分组切出 15% 作验证集（用于 XGBoost 早停 / 阈值选择）

输出（data/processed/）：
  数据集划分_训练集.csv、数据集划分_验证集.csv、数据集划分_测试集.csv、数据集划分_说明.md
"""
import os
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import train_models as tm  # noqa: E402

OUT = os.path.join(tm.ROOT, "data", "processed")
VALID_SIZE = 0.15


def main():
    from sklearn.model_selection import GroupShuffleSplit

    df = pd.read_csv(tm.DATA, encoding="utf-8-sig")
    print("全量样本:", len(df))

    train_pool, test, dropped = tm.split_strict(df)
    train, valid = tm.split_train_valid(train_pool, VALID_SIZE)
    dropped_pool = len(train_pool) - len(train) - len(valid)

    files = [("数据集划分_训练集.csv", train), ("数据集划分_验证集.csv", valid),
             ("数据集划分_测试集.csv", test)]
    for name, part in files:
        p = os.path.join(OUT, name)
        part.to_csv(p, index=False, encoding="utf-8-sig")
        print("  %-26s %6d 行 ｜ 正样本 %5d（%.1f%%）｜ 简历 %3d 份 ｜ 岗位 %4d 个" % (
            name, len(part), int(part[tm.LABEL].sum()),
            part[tm.LABEL].mean() * 100, part[tm.RESUME_ID].nunique(),
            part[tm.JOB_ID].nunique()))

    # 一致性校验
    assert len(set(train[tm.RESUME_ID]) & set(test[tm.RESUME_ID])) == 0
    assert len(set(train[tm.JOB_ID]) & set(test[tm.JOB_ID])) == 0
    assert len(set(valid[tm.RESUME_ID]) & set(train[tm.RESUME_ID])) == 0
    assert len(set(valid[tm.JOB_ID]) & set(train[tm.JOB_ID])) == 0
    assert len(set(valid[tm.RESUME_ID]) & set(test[tm.RESUME_ID])) == 0
    assert len(set(valid[tm.JOB_ID]) & set(test[tm.JOB_ID])) == 0
    assert len(train) + len(valid) + len(test) + dropped + dropped_pool == len(df)
    print("校验通过：训练/验证/测试 三份互不重叠（简历与岗位都不重叠）")
    print("  训练池内交叉丢弃: %d 条 ｜ 简历×岗位全交叉丢弃: %d 条" % (dropped_pool, dropped))

    md = build_md(df, train, valid, test, dropped, dropped_pool)
    with open(os.path.join(OUT, "数据集划分_说明.md"), "w", encoding="utf-8") as f:
        f.write(md + "\n")
    print("输出目录:", OUT)


def build_md(df, train, valid, test, dropped, dropped_pool):
    n = len(df)
    L = []
    L.append("# 数据集划分说明（任务5 · 评分模型）\n")
    L.append("> 全量样本：`data/processed/匹配特征_全量样本.csv` —— **该文件是 153,872 条全量标注样本**（含 12 个特征 + 标签），")
    L.append("> 文件名是早期命名，容易误解成“只有训练集”；实际的三份划分如下（由 `src/models/scoring/split_dataset.py` 生成）。\n")
    L.append("---\n")
    L.append("## 一、三个划分文件\n")
    L.append("| 文件 | 行数 | 正样本 | 正样本占该集 | 简历数 | 岗位数 |")
    L.append("|---|---|---|---|---|---|")
    for name, part in [("`数据集划分_训练集.csv`", train), ("`数据集划分_验证集.csv`", valid),
                       ("`数据集划分_测试集.csv`", test)]:
        L.append("| %s | %d | %d | %.1f%% | %d | %d |" % (
            name, len(part), int(part["标签"].sum()), part["标签"].mean() * 100,
            part["简历ID"].nunique(), part["岗位ID"].nunique()))
    L.append("| （未使用）训练池内交叉配对 | %d | — | — | — | — |" % dropped_pool)
    L.append("| （未使用）简历×岗位全交叉配对 | %d | — | — | — | — |" % dropped)
    L.append("| **合计** | **%d** | %d | %.1f%% | %d | %d |" % (
        n, int(df["标签"].sum()), df["标签"].mean() * 100,
        df["简历ID"].nunique(), df["岗位ID"].nunique()))
    L.append("")
    L.append("## 二、划分规则（与训练脚本一致，种子 42）\n")
    L.append("1. **严格划分（防数据泄漏）**：")
    L.append("   - 训练集 = 训练简历 × 训练岗位；测试集 = 测试简历 × 测试岗位；")
    L.append("   - 一份简历会产生几十~几百条配对、一个岗位也会出现在多条配对里，若只按行随机划分，")
    L.append("     模型能“背下”简历/岗位的个体特征，指标会虚高，因此简历与岗位两侧都隔开；")
    L.append("   - 两侧交叉的 %d 条配对**不使用**（既不属于训练也不属于测试）。" % dropped)
    L.append("2. **验证集**：在训练池内再切出 %.0f%%（简历与岗位都与训练集不重叠），用于 XGBoost 早停与决策阈值选择，" % (VALID_SIZE * 100))
    L.append("   测试集从头到尾只用于最终评估。\n")
    L.append("## 三、校验结果\n")
    L.append("- 训练 ∩ 测试：简历重叠 **0** 个、岗位重叠 **0** 个；")
    L.append("- 训练 ∩ 验证：简历重叠 **0** 个、岗位重叠 **0** 个；")
    L.append("- 验证 ∩ 测试：简历重叠 **0** 个、岗位重叠 **0** 个；")
    L.append("- 训练 + 验证 + 测试 + 未使用（%d + %d）= %d，与全量样本数一致。\n" %
             (dropped_pool, dropped, n))
    L.append("## 四、怎么复现/使用\n")
    L.append("```bash")
    L.append("python src/models/scoring/build_labels.py     # 1) 生成配对标签")
    L.append("python src/models/scoring/build_features.py   # 2) 生成特征矩阵（全量样本）")
    L.append("python src/models/scoring/split_dataset.py    # 3) 切分训练/验证/测试集（本步骤）")
    L.append("python src/models/scoring/train_models.py     # 4) 训练与评估（内部使用同样的切分逻辑）")
    L.append("```")
    L.append("")
    L.append("> 训练脚本 `train_models.py` 内部用同一套切分函数（同样的种子与分组方式），"
             "因此直接跑训练脚本得到的训练/验证/测试集与本目录三个文件**完全一致**，指标可直接对应。\n")
    return "\n".join(L)


if __name__ == "__main__":
    main()
