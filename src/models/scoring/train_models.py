# -*- coding: utf-8 -*-
"""
任务5 · 评分模型训练与评估

基线：Logistic 回归（精度基线）
对比：SVM（线性核）、随机森林
上线：XGBoost（梯度提升树，最终模型）

数据：data/processed/匹配特征_全量样本.csv（153,872 条配对样本 × 12 个特征；内部按严格规则切分）

两种划分（都用 GroupShuffleSplit，随机种子 42）：
  ① 严格划分（主口径）：简历与岗位**都不重叠** —— 训练集取"训练简历 × 训练岗位"的配对，
     测试集取"测试简历 × 测试岗位"的配对，两侧交叉的配对丢弃，彻底避免配对记忆式泄漏；
  ② 参考划分：仅按简历分组（岗位会重叠），用于观察泄漏对指标的影响。

最终上线模型：用**全部样本**重新训练的 XGBoost（特征顺序写入元信息）

输出：
  data/processed/模型评估结果.csv / 模型评估结果_参考划分.csv
  data/processed/模型特征重要性.csv
  data/processed/评分模型_评估报告.md
  models/xgboost_scoring_model.json、models/model_metadata.json
  reports/figures/模型对比_*.png
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DATA = os.path.join(ROOT, "data", "processed", "匹配特征_全量样本.csv")
FIG_DIR = os.path.join(ROOT, "reports", "figures")
MODEL_DIR = os.path.join(ROOT, "models")
OUT_DIR = os.path.join(ROOT, "data", "processed")
for d in (FIG_DIR, MODEL_DIR, OUT_DIR):
    os.makedirs(d, exist_ok=True)

FEATURES = ["城市匹配度", "学历匹配度", "经验是否满足", "经验差值", "经验差值归一化",
            "技能Jaccard", "核心技能命中率", "技能覆盖度",
            "岗位-经历文本相似度", "岗位-求职意向相似度", "专业匹配度", "证书命中数"]
LABEL = "标签"
RESUME_ID, JOB_ID = "简历ID", "岗位ID"
TEST_SIZE = 0.20
SEED = 42
XGB_PARAMS = dict(n_estimators=600, learning_rate=0.1, max_depth=6, subsample=0.8,
                  colsample_bytree=0.8, min_child_weight=1, reg_lambda=1.0,
                  tree_method="hist", eval_metric="logloss",
                  early_stopping_rounds=40, random_state=SEED, n_jobs=-1)


def setup_font():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 110
    return plt


def has_xgb():
    try:
        import xgboost  # noqa: F401
        return True
    except Exception:
        return False


def split_strict(df):
    """简历与岗位都不重叠的划分"""
    from sklearn.model_selection import GroupShuffleSplit
    r_tr, r_te = next(GroupShuffleSplit(1, test_size=TEST_SIZE, random_state=SEED)
                      .split(df, groups=df[RESUME_ID]))
    j_tr, j_te = next(GroupShuffleSplit(1, test_size=TEST_SIZE, random_state=SEED)
                      .split(df, groups=df[JOB_ID]))
    tr_res, te_res = set(df.iloc[r_tr][RESUME_ID]), set(df.iloc[r_te][RESUME_ID])
    tr_job, te_job = set(df.iloc[j_tr][JOB_ID]), set(df.iloc[j_te][JOB_ID])
    train = df[df[RESUME_ID].isin(tr_res) & df[JOB_ID].isin(tr_job)]
    test = df[df[RESUME_ID].isin(te_res) & df[JOB_ID].isin(te_job)]
    dropped = len(df) - len(train) - len(test)
    return train, test, dropped


def split_by_resume(df):
    """参考划分：只保证简历不重叠"""
    from sklearn.model_selection import GroupShuffleSplit
    tr, te = next(GroupShuffleSplit(1, test_size=TEST_SIZE, random_state=SEED)
                  .split(df, groups=df[RESUME_ID]))
    return df.iloc[tr], df.iloc[te]


def split_train_valid(train_pool, valid_size=0.15):
    """在训练池内再切出验证集：简历与岗位都与训练集不重叠（用于早停/阈值选择）"""
    from sklearn.model_selection import GroupShuffleSplit
    r_tr, r_va = next(GroupShuffleSplit(1, test_size=valid_size, random_state=SEED)
                      .split(train_pool, groups=train_pool[RESUME_ID]))
    j_tr, j_va = next(GroupShuffleSplit(1, test_size=valid_size, random_state=SEED)
                      .split(train_pool, groups=train_pool[JOB_ID]))
    tr_res = set(train_pool.iloc[r_tr][RESUME_ID]); va_res = set(train_pool.iloc[r_va][RESUME_ID])
    tr_job = set(train_pool.iloc[j_tr][JOB_ID]); va_job = set(train_pool.iloc[j_va][JOB_ID])
    train = train_pool[train_pool[RESUME_ID].isin(tr_res) & train_pool[JOB_ID].isin(tr_job)]
    valid = train_pool[train_pool[RESUME_ID].isin(va_res) & train_pool[JOB_ID].isin(va_job)]
    return train, valid


def build_linear_models():
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import LinearSVC
    return {
        "Logistic回归（基线）": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=2000, random_state=SEED))]),
        "SVM（线性核）": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LinearSVC(C=1.0, max_iter=5000, random_state=SEED))]),
        "随机森林": RandomForestClassifier(n_estimators=300, n_jobs=-1, random_state=SEED),
    }


def evaluate(name, y_true, y_pred, y_score, fit_time, pred_time):
    from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                                 precision_score, recall_score, roc_auc_score)
    return {
        "模型": name,
        "Accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "Precision": round(float(precision_score(y_true, y_pred)), 4),
        "Recall": round(float(recall_score(y_true, y_pred)), 4),
        "F1": round(float(f1_score(y_true, y_pred)), 4),
        "ROC-AUC": round(float(roc_auc_score(y_true, y_score)), 4),
        "训练耗时(s)": round(fit_time, 2),
        "预测耗时(s)": round(pred_time, 3),
        "_cm": confusion_matrix(y_true, y_pred).tolist(),
        "_y_score": y_score,
    }


def run_setting(tag, train, test, use_xgb, valid=None):
    """训练 4 个模型并评估；返回 (指标行列表, 模型字典, 分数字典, xgb模型)"""
    X_tr, y_tr = train[FEATURES], train[LABEL]
    X_te, y_te = test[FEATURES], test[LABEL]
    rows, scores, fitted = [], {}, {}
    print("\n===== %s ｜ 训练 %d / 测试 %d =====" % (tag, len(train), len(test)))
    for name, clf in build_linear_models().items():
        t0 = time.time(); clf.fit(X_tr, y_tr); fit_t = time.time() - t0
        t1 = time.time(); y_pred = clf.predict(X_te)
        y_score = clf.predict_proba(X_te)[:, 1] if hasattr(clf, "predict_proba") else clf.decision_function(X_te)
        pred_t = time.time() - t1
        r = evaluate(name, y_te, y_pred, y_score, fit_t, pred_t)
        rows.append(r); scores[name] = r.pop("_y_score"); fitted[name] = clf
        print("  %-16s Acc=%.4f  F1=%.4f  AUC=%.4f  (%.2fs)" %
              (name, r["Accuracy"], r["F1"], r["ROC-AUC"], fit_t))
    xgb_model = None
    if use_xgb:
        from xgboost import XGBClassifier
        params = dict(XGB_PARAMS)
        if valid is None:
            params.pop("early_stopping_rounds", None)   # 无验证集时关闭早停
        clf = XGBClassifier(**params)
        t0 = time.time()
        if valid is not None:
            clf.fit(X_tr, y_tr, eval_set=[(valid[FEATURES], valid[LABEL])], verbose=False)
        else:
            clf.fit(X_tr, y_tr, verbose=False)
        fit_t = time.time() - t0
        t1 = time.time(); y_pred = clf.predict(X_te); y_score = clf.predict_proba(X_te)[:, 1]
        pred_t = time.time() - t1
        r = evaluate("XGBoost（上线模型）", y_te, y_pred, y_score, fit_t, pred_t)
        r["best_iteration"] = int(getattr(clf, "best_iteration", -1) or -1)
        rows.append(r); scores["XGBoost（上线模型）"] = r.pop("_y_score"); fitted["XGBoost（上线模型）"] = clf
        xgb_model = clf
        print("  %-16s Acc=%.4f  F1=%.4f  AUC=%.4f  (%.2fs, best_iter=%s)" %
              ("XGBoost", r["Accuracy"], r["F1"], r["ROC-AUC"], fit_t, r.get("best_iteration")))
    return rows, fitted, scores, xgb_model, y_te


def main():
    plt = setup_font()
    from sklearn.model_selection import GroupShuffleSplit
    use_xgb = has_xgb()
    if not use_xgb:
        print("!! 未安装 xgboost，本次跳过 XGBoost（安装后重跑即可）")

    df = pd.read_csv(DATA, encoding="utf-8-sig")
    print("样本:", len(df), "｜特征:", len(FEATURES), "｜正样本占比: %.2f%%" % (df[LABEL].mean() * 100))

    # ---------- ① 严格划分 ----------
    train_s, test_s, dropped = split_strict(df)
    print("严格划分：训练 %d（简历 %d / 岗位 %d）｜测试 %d（简历 %d / 岗位 %d）｜丢弃交叉配对 %d" % (
        len(train_s), train_s[RESUME_ID].nunique(), train_s[JOB_ID].nunique(),
        len(test_s), test_s[RESUME_ID].nunique(), test_s[JOB_ID].nunique(), dropped))
    print("  测试集与训练集 简历重叠 %d 个、岗位重叠 %d 个" % (
        len(set(train_s[RESUME_ID]) & set(test_s[RESUME_ID])),
        len(set(train_s[JOB_ID]) & set(test_s[JOB_ID]))))
    train_s2, valid_s = split_train_valid(train_s)
    print("  训练池 %d → 训练集 %d（简历 %d / 岗位 %d）｜验证集 %d（简历 %d / 岗位 %d）" % (
        len(train_s), len(train_s2), train_s2[RESUME_ID].nunique(), train_s2[JOB_ID].nunique(),
        len(valid_s), valid_s[RESUME_ID].nunique(), valid_s[JOB_ID].nunique()))

    rows_strict, fitted, scores_strict, xgb_strict, y_te = run_setting(
        "严格划分（简历+岗位均不重叠）", train_s2, test_s, use_xgb, valid_s)

    # ---------- ①b XGBoost 小网格调参（只在训练/验证集上做） ----------
    tune_records, best_params = [], None
    threshold_info = None
    if use_xgb:
        print("\n===== XGBoost 小网格调参（按验证集 F1→AUC 选最优）=====")
        best_params, best_rec, tune_records, best_clf = tune_xgb(train_s2, valid_s)
        from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                                     precision_score, recall_score, roc_auc_score)
        X_te, y_te2 = test_s[FEATURES], test_s[LABEL]
        t1 = time.time()
        y_pred = best_clf.predict(X_te)
        y_score = best_clf.predict_proba(X_te)[:, 1]
        pred_t = time.time() - t1
        r = evaluate("XGBoost（上线模型）", y_te2, y_pred, y_score,
                     best_rec["训练耗时(s)"], pred_t)
        r["best_iteration"] = best_rec["best_iteration"]
        r["最优参数"] = "depth=%d, lr=%.2f, n_est=%d" % (
            best_rec["max_depth"], best_rec["learning_rate"], best_rec["n_estimators(上限)"])
        rows_strict = [x for x in rows_strict if not str(x["模型"]).startswith("XGBoost")] + [r]
        scores_strict[r["模型"]] = r.pop("_y_score")
        xgb_strict = best_clf
        print("  最优配置：%s → 测试 Acc=%.4f F1=%.4f AUC=%.4f" % (
            r["最优参数"], r["Accuracy"], r["F1"], r["ROC-AUC"]))

        # 决策阈值调优（在验证集上按 F1 网格搜索，再应用到测试集）
        from sklearn.metrics import f1_score as _f1
        p_va = best_clf.predict_proba(valid_s[FEATURES])[:, 1]
        grid_t = np.round(np.arange(0.05, 1.0, 0.05), 3)
        f1_grid = np.array([_f1(valid_s[LABEL], (p_va >= t).astype(int)) for t in grid_t])
        best_f1 = float(f1_grid.max())
        cand = grid_t[f1_grid >= best_f1 - 1e-9]        # 达到验证集最优 F1 的所有阈值
        best_t = float(cand[np.argmin(np.abs(cand - 0.5))]) if len(cand) else 0.5
        y_pred_t = (y_score >= best_t).astype(int)
        r_t = evaluate("XGBoost（阈值调优后）", y_te2, y_pred_t, y_score,
                       best_rec["训练耗时(s)"], pred_t)
        r_t["决策阈值"] = round(best_t, 3)
        r_t.pop("best_iteration", None)
        print("  阈值调优：验证集最优阈值=%.3f → 测试 Acc=%.4f F1=%.4f（阈值 0.5 时为 %.4f/%.4f）" %
              (best_t, r_t["Accuracy"], r_t["F1"], r["Accuracy"], r["F1"]))
        threshold_info = {"推荐阈值": round(best_t, 3), "阈值0.5": {
            "Accuracy": r["Accuracy"], "Precision": r["Precision"],
            "Recall": r["Recall"], "F1": r["F1"]},
            "调优阈值": {"Accuracy": r_t["Accuracy"], "Precision": r_t["Precision"],
                     "Recall": r_t["Recall"], "F1": r_t["F1"]}}

    # ---------- ② 参考划分（仅简历不重叠） ----------
    train_r, test_r = split_by_resume(df)
    train_r2, valid_r = split_train_valid(train_r)
    rows_ref, _, scores_ref, _, y_te_ref = run_setting(
        "参考划分（仅简历不重叠，岗位重叠 %d 个）" %
        len(set(train_r[JOB_ID]) & set(test_r[JOB_ID])),
        train_r2, test_r, use_xgb, valid_r)

    # ---------- ③ 最终上线模型：全量数据重训 ----------
    best_iter = next((r.get("best_iteration", -1) for r in rows_strict
                      if r["模型"].startswith("XGBoost")), -1)
    xgb_full = None
    if use_xgb:
        from xgboost import XGBClassifier
        params = dict(best_params) if best_params else dict(XGB_PARAMS)
        params.pop("early_stopping_rounds", None)
        params["n_estimators"] = best_iter if best_iter and best_iter > 0 else 400
        print("\n===== 最终上线模型：全量 %d 条样本重训 XGBoost（%s, n_estimators=%d）=====" %
              (len(df), "depth=%s lr=%s" % (params.get("max_depth"), params.get("learning_rate")),
               params["n_estimators"]))
        t0 = time.time()
        xgb_full = XGBClassifier(**params)
        xgb_full.fit(df[FEATURES], df[LABEL], verbose=False)
        print("  完成，耗时 %.1fs" % (time.time() - t0))
        xgb_full.save_model(os.path.join(MODEL_DIR, "xgboost_scoring_model.json"))

    # ---------- 输出指标 ----------
    def tidy(rows):
        out = []
        for r in rows:
            r = dict(r)
            bi = r.pop("best_iteration", None)
            if bi is not None:
                r["best_iteration"] = bi
            out.append(r)
        return pd.DataFrame(out)

    res_strict = tidy(rows_strict)
    res_ref = tidy(rows_ref)
    res_strict.drop(columns=["_cm"], errors="ignore").to_csv(
        os.path.join(OUT_DIR, "模型评估结果.csv"), index=False, encoding="utf-8-sig")
    res_ref.drop(columns=["_cm"], errors="ignore").to_csv(
        os.path.join(OUT_DIR, "模型评估结果_参考划分.csv"), index=False, encoding="utf-8-sig")
    print("\n【严格划分指标】")
    show = ["模型", "Accuracy", "Precision", "Recall", "F1", "ROC-AUC", "训练耗时(s)"]
    print(res_strict[show].to_string(index=False))
    print("\n【参考划分指标（岗位有重叠）】")
    print(res_ref[show].to_string(index=False))

    # ---------- 特征重要性 ----------
    imp_rows = []
    for f, v in zip(FEATURES, fitted["随机森林"].feature_importances_):
        imp_rows.append(["随机森林", f, round(float(v), 6)])
    if xgb_strict is not None:
        for f, v in zip(FEATURES, xgb_strict.feature_importances_):
            imp_rows.append(["XGBoost（严格划分）", f, round(float(v), 6)])
    if xgb_full is not None:
        for f, v in zip(FEATURES, xgb_full.feature_importances_):
            imp_rows.append(["XGBoost（全量上线模型）", f, round(float(v), 6)])
    imp_df = pd.DataFrame(imp_rows, columns=["模型", "特征", "重要性"])
    imp_df.to_csv(os.path.join(OUT_DIR, "模型特征重要性.csv"), index=False, encoding="utf-8-sig")
    if tune_records:
        pd.DataFrame(tune_records).to_csv(
            os.path.join(OUT_DIR, "模型调参记录.csv"), index=False, encoding="utf-8-sig")

    # ---------- ①c 难样本子集评估（正样本 + 只差 1 项门槛的负样本） ----------
    hard_rows = []
    if "未满足维度数" in df.columns:
        hard_mask = (test_s["未满足维度数"] == 1) | (test_s[LABEL] == 1)
        hard = test_s[hard_mask]
        print("\n【难样本子集】测试集内 正样本+只差1项门槛的负样本：%d 条（占测试集 %.1f%%）" %
              (len(hard), len(hard) / len(test_s) * 100))
        all_fitted = dict(fitted)
        if xgb_strict is not None:
            all_fitted["XGBoost（上线模型）"] = xgb_strict
        for name, clf in all_fitted.items():
            yp = clf.predict(hard[FEATURES])
            ys = (clf.predict_proba(hard[FEATURES])[:, 1] if hasattr(clf, "predict_proba")
                  else clf.decision_function(hard[FEATURES]))
            from sklearn.metrics import (accuracy_score, f1_score, precision_score,
                                         recall_score, roc_auc_score)
            hard_rows.append({
                "模型": name,
                "样本数": len(hard),
                "Accuracy": round(float(accuracy_score(hard[LABEL], yp)), 4),
                "Precision": round(float(precision_score(hard[LABEL], yp)), 4),
                "Recall": round(float(recall_score(hard[LABEL], yp)), 4),
                "F1": round(float(f1_score(hard[LABEL], yp)), 4),
                "ROC-AUC": round(float(roc_auc_score(hard[LABEL], ys)), 4),
            })
        hard_df = pd.DataFrame(hard_rows)
        hard_df.to_csv(os.path.join(OUT_DIR, "模型评估结果_难样本子集.csv"),
                       index=False, encoding="utf-8-sig")
        print(hard_df.to_string(index=False))
    else:
        hard_df = None

    # ---------- 图表 ----------
    charts = make_charts(plt, res_strict, res_ref, rows_strict, scores_strict, y_te, imp_df)

    # ---------- 元信息 ----------
    meta = {
        "model": "XGBoost (XGBClassifier)",
        "purpose": "人岗匹配评分（二分类：匹配 / 不匹配）",
        "features": FEATURES,
        "n_features": len(FEATURES),
        "feature_usage": "推理时按 features 顺序构造 12 维特征；predict_proba 输出匹配概率",
        "trained_on": "全部 %d 条配对样本（最终上线模型）" % len(df),
        "eval_split_strict": {
            "train": int(len(train_s2)), "valid": int(len(valid_s)), "test": int(len(test_s)),
            "dropped_cross_pairs": int(dropped),
            "resume_overlap": 0, "job_overlap": 0,
        },
        "eval_split_reference": {
            "train": int(len(train_r2)), "valid": int(len(valid_r)), "test": int(len(test_r)),
            "job_overlap": int(len(set(train_r[JOB_ID]) & set(test_r[JOB_ID]))),
        },
        "metrics_strict": {r["模型"]: {k: v for k, v in r.items() if not k.startswith("_")}
                           for r in rows_strict},
        "metrics_reference": {r["模型"]: {k: v for k, v in r.items() if not k.startswith("_")}
                              for r in rows_ref},
        "xgb_params_full": {k: v for k, v in XGB_PARAMS.items() if k != "early_stopping_rounds"},
        "best_iteration_strict": int(best_iter),
        "xgb_best_params": best_params or None,
        "recommended_threshold": (threshold_info or {}).get("推荐阈值"),
        "threshold_metrics": threshold_info,
        "tuning_records": "data/processed/模型调参记录.csv",
        "model_file": "models/xgboost_scoring_model.json",
    }
    with open(os.path.join(MODEL_DIR, "model_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    report = build_report(res_strict, res_ref, rows_strict, imp_df, meta, len(df), dropped,
                          xgb_strict is not None, xgb_full is not None, hard_df=hard_df,
                          threshold_info=threshold_info)
    with open(os.path.join(OUT_DIR, "评分模型_评估报告.md"), "w", encoding="utf-8") as f:
        f.write(report + "\n")

    print("\n图表：")
    for c in charts:
        print("  ", os.path.relpath(c, ROOT))
    print("报告：data/processed/评分模型_评估报告.md")
    if xgb_full is not None:
        print("上线模型：models/xgboost_scoring_model.json")


def make_charts(plt, res_strict, res_ref, rows_strict, scores, y_te, imp_df):
    from sklearn.metrics import roc_curve
    out = []
    names = list(res_strict["模型"])
    colors = {n: c for n, c in zip(names, ["#8c8c8c", "#5b8ff9", "#5ad8a6", "#e8684a", "#f6bd16"])}

    # 1) 指标对比（严格划分 vs 参考划分）
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.8))
    metrics = ["Accuracy", "Precision", "Recall", "F1", "ROC-AUC"]
    x = np.arange(len(metrics)); w = 0.2
    for i, name in enumerate(names):
        row = res_strict[res_strict["模型"] == name].iloc[0]
        vals = [row[m] for m in metrics]
        axes[0].bar(x + i * w, vals, w, label=name, color=colors[name])
        for xi, v in zip(x + i * w, vals):
            axes[0].text(xi, v + 0.0005, "%.3f" % v, ha="center", fontsize=6.5, rotation=90)
    axes[0].set_xticks(x + w * 1.5); axes[0].set_xticklabels(metrics)
    lo = min(res_strict[m].min() for m in metrics)
    axes[0].set_ylim(max(0.9, lo - 0.02), 1.002)
    axes[0].set_title("严格划分（简历+岗位均不重叠）四模型指标")
    axes[0].legend(fontsize=8, loc="lower left"); axes[0].grid(axis="y", ls="--", alpha=0.4)

    idx = np.arange(len(names)); w2 = 0.36
    axes[1].bar(idx - w2 / 2, res_strict["ROC-AUC"], w2, label="严格划分", color="#3182bd")
    axes[1].bar(idx + w2 / 2, res_ref.set_index("模型").loc[names, "ROC-AUC"], w2,
                label="参考划分（岗位重叠）", color="#f6bd16")
    for i, n in enumerate(names):
        axes[1].text(i - w2 / 2, res_strict["ROC-AUC"].iloc[i] + 0.0004,
                     "%.4f" % res_strict["ROC-AUC"].iloc[i], ha="center", fontsize=7)
        axes[1].text(i + w2 / 2, res_ref.set_index("模型").loc[n, "ROC-AUC"] + 0.0004,
                     "%.4f" % res_ref.set_index("模型").loc[n, "ROC-AUC"], ha="center", fontsize=7)
    axes[1].set_xticks(idx); axes[1].set_xticklabels(names, fontsize=8)
    axes[1].set_ylim(0.99, 1.001); axes[1].set_title("ROC-AUC：划分口径对比（数据泄漏影响）")
    axes[1].legend(fontsize=8); axes[1].grid(axis="y", ls="--", alpha=0.4)
    plt.tight_layout()
    p = os.path.join(FIG_DIR, "模型对比_指标与耗时.png"); plt.savefig(p, bbox_inches="tight"); plt.close()
    out.append(p)

    # 2) ROC 曲线
    plt.figure(figsize=(6.6, 6))
    for name in names:
        fpr, tpr, _ = roc_curve(y_te, scores[name])
        auc = res_strict[res_strict["模型"] == name].iloc[0]["ROC-AUC"]
        plt.plot(fpr, tpr, label="%s (AUC=%.5f)" % (name, auc), color=colors[name], lw=2)
    plt.plot([0, 1], [0, 1], "k--", lw=1, label="随机猜测")
    plt.xlabel("假正率 FPR"); plt.ylabel("真正率 TPR")
    plt.title("ROC 曲线（严格划分测试集）")
    plt.legend(fontsize=8, loc="lower right"); plt.grid(ls="--", alpha=0.4)
    p = os.path.join(FIG_DIR, "模型对比_ROC曲线.png"); plt.savefig(p, bbox_inches="tight"); plt.close()
    out.append(p)

    # 3) 混淆矩阵
    fig, axes = plt.subplots(1, len(rows_strict), figsize=(4.2 * len(rows_strict), 3.9))
    for ax, r in zip(np.atleast_1d(axes), rows_strict):
        cm = np.array(r["_cm"])
        ax.imshow(cm, cmap="Blues")
        for i in range(2):
            for j in range(2):
                ax.text(j, i, str(cm[i, j]), ha="center", va="center", fontsize=11,
                        color="white" if cm[i, j] > cm.max() / 2 else "black")
        ax.set_title(r["模型"], fontsize=9.5)
        ax.set_xticks([0, 1]); ax.set_xticklabels(["预测不匹配", "预测匹配"], fontsize=8)
        ax.set_yticks([0, 1]); ax.set_yticklabels(["实际不匹配", "实际匹配"], fontsize=8)
    plt.tight_layout()
    p = os.path.join(FIG_DIR, "模型对比_混淆矩阵.png"); plt.savefig(p, bbox_inches="tight"); plt.close()
    out.append(p)

    # 4) 特征重要性
    keys = [k for k in imp_df["模型"].unique()]
    fig, axes = plt.subplots(1, len(keys), figsize=(6.2 * len(keys), 4.8))
    for ax, m in zip(np.atleast_1d(axes), keys):
        sub = imp_df[imp_df["模型"] == m].sort_values("重要性")
        ax.barh(sub["特征"], sub["重要性"],
                color="#3182bd" if "XGBoost" in m else "#5ad8a6")
        ax.set_title("%s 特征重要性" % m, fontsize=10)
        ax.grid(axis="x", ls="--", alpha=0.4)
    plt.tight_layout()
    p = os.path.join(FIG_DIR, "模型对比_特征重要性.png"); plt.savefig(p, bbox_inches="tight"); plt.close()
    out.append(p)
    return out


def tune_xgb(train, valid):
    """小网格调参：以【验证集】F1→AUC 选最优配置（不接触测试集）"""
    from sklearn.metrics import f1_score, roc_auc_score
    from xgboost import XGBClassifier
    grid = [
        dict(max_depth=4, learning_rate=0.10, n_estimators=300),
        dict(max_depth=6, learning_rate=0.10, n_estimators=300),
        dict(max_depth=6, learning_rate=0.05, n_estimators=600),
        dict(max_depth=8, learning_rate=0.10, n_estimators=300),
        dict(max_depth=8, learning_rate=0.05, n_estimators=600),
        dict(max_depth=10, learning_rate=0.10, n_estimators=400),
        dict(max_depth=12, learning_rate=0.10, n_estimators=400),
    ]
    X_tr, y_tr = train[FEATURES], train[LABEL]
    X_va, y_va = valid[FEATURES], valid[LABEL]
    records, best = [], None
    for g in grid:
        params = dict(XGB_PARAMS)
        params.update(g)
        params["early_stopping_rounds"] = 40
        clf = XGBClassifier(**params)
        t0 = time.time()
        clf.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        fit_t = time.time() - t0
        p = clf.predict(X_va)
        s = clf.predict_proba(X_va)[:, 1]
        f1v, aucv = f1_score(y_va, p), roc_auc_score(y_va, s)
        rec = {"max_depth": g["max_depth"], "learning_rate": g["learning_rate"],
               "n_estimators(上限)": g["n_estimators"],
               "best_iteration": int(getattr(clf, "best_iteration", -1) or -1),
               "验证集F1": round(float(f1v), 5), "验证集AUC": round(float(aucv), 6),
               "训练耗时(s)": round(fit_t, 2)}
        records.append(rec)
        print("    depth=%2d lr=%.2f n=%3d → 验证F1=%.5f AUC=%.6f (best_iter=%s)" %
              (g["max_depth"], g["learning_rate"], g["n_estimators"], f1v, aucv, rec["best_iteration"]))
        key = (f1v, aucv)
        if best is None or key > best[0]:
            best = (key, dict(params), rec, clf)
    return best[1], best[2], records, best[3]


def build_report(res_strict, res_ref, rows_strict, imp_df, meta, n_all, dropped,
                 has_xgb_eval, has_xgb_full, hard_df=None, threshold_info=None):
    L = []
    L.append("# 评分模型训练与评估报告（任务5 · 评分模型搭建）\n")
    L.append("> 数据：`data/processed/匹配特征_全量样本.csv`（%d 条配对样本 × 12 个特征）" % n_all)
    L.append("> 代码：`src/models/scoring/train_models.py`（固定随机种子 %d，可复现）" % SEED)
    L.append("> 模型：**Logistic 回归（精度基线）** → SVM（线性核）/ 随机森林（对比） → **XGBoost（最终上线模型）**\n")
    L.append("---\n")
    L.append("## 一、训练/测试集划分（重点：避免数据泄漏）\n")
    L.append("| 口径 | 训练集 | 验证集 | 测试集 | 简历重叠 | 岗位重叠 | 说明 |")
    L.append("|---|---|---|---|---|---|---|")
    L.append("| **严格划分（主口径）** | %d | %d | %d | 0 | 0 | 训练集 = 训练简历 × 训练岗位；测试集 = 测试简历 × 测试岗位；验证集在训练池内再切分且与训练集不重叠；两侧交叉的 %d 条配对丢弃 |"
             % (meta["eval_split_strict"]["train"], meta["eval_split_strict"]["valid"],
                meta["eval_split_strict"]["test"], dropped))
    L.append("| 参考划分 | %d | %d | %d | 0 | %d | 只保证简历不重叠，岗位会同时出现在两侧 |"
             % (meta["eval_split_reference"]["train"], meta["eval_split_reference"]["valid"],
                meta["eval_split_reference"]["test"],
                meta["eval_split_reference"]["job_overlap"]))
    L.append("")
    L.append("> 同一份简历会产生几十~几百条配对、同一个岗位也会出现在多条配对中，若只按行随机划分，"
             "模型可以“背下”简历/岗位的个体特征，指标会虚高。严格划分把简历与岗位**两侧都隔开**"
             "（验证集同样与训练集不重叠，只用于早停与阈值选择），评估更可信。\n")
    L.append("## 二、模型指标对比（严格划分测试集）\n")
    cols = ["模型", "Accuracy", "Precision", "Recall", "F1", "ROC-AUC", "训练耗时(s)", "预测耗时(s)"]
    L.append("| " + " | ".join(cols) + " |")
    L.append("|" + "---|" * len(cols))
    for _, r in res_strict.iterrows():
        L.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    L.append("")
    best = res_strict.sort_values("ROC-AUC", ascending=False).iloc[0]
    base = res_strict[res_strict["模型"].str.contains("Logistic")].iloc[0]
    L.append("- **最优模型：%s**（ROC-AUC %.4f，F1 %.4f，Accuracy %.4f）；" %
             (best["模型"], best["ROC-AUC"], best["F1"], best["Accuracy"]))
    L.append("- 相对 Logistic 基线：ROC-AUC %+.4f、F1 %+.4f、Accuracy %+.4f；" %
             (best["ROC-AUC"] - base["ROC-AUC"], best["F1"] - base["F1"],
              best["Accuracy"] - base["Accuracy"]))
    L.append("- 训练耗时：Logistic %.2fs、随机森林 %.2fs%s。\n" % (
        base["训练耗时(s)"],
        res_strict[res_strict["模型"] == "随机森林"].iloc[0]["训练耗时(s)"],
        ("、XGBoost %.2fs" % res_strict[res_strict["模型"].str.startswith("XGBoost")].iloc[0]["训练耗时(s)"])
        if has_xgb_eval else ""))
    L.append("### 2.1 划分口径对比（数据泄漏的影响）\n")
    cols2 = ["模型", "Accuracy", "F1", "ROC-AUC"]
    L.append("| 模型 | 严格划分 Acc | 参考划分 Acc | 严格划分 AUC | 参考划分 AUC |")
    L.append("|---|---|---|---|---|")
    ref = res_ref.set_index("模型")
    for _, r in res_strict.iterrows():
        m = r["模型"]
        if m in ref.index:
            L.append("| %s | %.4f | %.4f | %.4f | %.4f |" %
                     (m, r["Accuracy"], ref.loc[m, "Accuracy"], r["ROC-AUC"], ref.loc[m, "ROC-AUC"]))
    L.append("")
    L.append("> 参考划分（岗位重叠）下各模型指标普遍更高，说明确实存在配对记忆带来的虚高；"
             "因此**本报告以严格划分结果为准**。\n")
    if hard_df is not None and not hard_df.empty:
        L.append("### 2.2 难样本子集评估（正样本 + 只差 1 项门槛的负样本）\n")
        L.append("> 全测试集里大多数负样本“差得很多”，容易被区分；把负样本限制为**只差 1 个门槛**的近似岗位"
                 "（即最容易被误判为匹配的样本），更能体现模型差异。\n")
        cols_h = ["模型", "样本数", "Accuracy", "Precision", "Recall", "F1", "ROC-AUC"]
        L.append("| " + " | ".join(cols_h) + " |")
        L.append("|" + "---|" * len(cols_h))
        for _, r in hard_df.iterrows():
            L.append("| " + " | ".join(str(r[c]) for c in cols_h) + " |")
        L.append("")
        hb = hard_df.sort_values("F1", ascending=False).iloc[0]
        hl = hard_df[hard_df["模型"].str.contains("Logistic")].iloc[0]
        L.append("- 难样本子集上最优：**%s**（F1 %.4f）；Logistic 基线 F1 %.4f，差距 **%+.4f**。" %
                 (hb["模型"], hb["F1"], hl["F1"], hb["F1"] - hl["F1"]))
        L.append("- 结论：样本越难，树模型相对线性模型的优势越明显（线性模型无法表达“多个门槛同时成立”的合取条件）。\n")
    if threshold_info:
        L.append("### 2.3 上线模型决策阈值调优（在验证集上按 F1 选阈值）\n")
        L.append("| 阈值 | Accuracy | Precision | Recall | F1 |")
        L.append("|---|---|---|---|---|")
        for label, key in [("0.5（默认）", "阈值0.5"), ("%.3f（推荐）" % threshold_info["推荐阈值"], "调优阈值")]:
            t = threshold_info[key]
            L.append("| %s | %.4f | %.4f | %.4f | %.4f |" %
                     (label, t["Accuracy"], t["Precision"], t["Recall"], t["F1"]))
        L.append("")
        L.append("> XGBoost 输出的是概率（logloss 训练），因此可以在验证集上按业务偏好选择阈值："
                 "降低阈值可提升 Recall（尽量不漏掉可匹配岗位），提高阈值可提升 Precision。"
                 "上线时把推荐阈值写入 `models/model_metadata.json`。\n")
    L.append("## 三、混淆矩阵（严格划分测试集）\n")
    for r in rows_strict:
        cm = r["_cm"]
        L.append("**%s**\n" % r["模型"])
        L.append("| | 预测不匹配 | 预测匹配 |")
        L.append("|---|---|---|")
        L.append("| 实际不匹配 | %d | %d |" % (cm[0][0], cm[0][1]))
        L.append("| 实际匹配 | %d | %d |\n" % (cm[1][0], cm[1][1]))
    L.append("## 四、特征重要性\n")
    for m in imp_df["模型"].unique():
        L.append("### %s\n" % m)
        L.append("| 排名 | 特征 | 重要性 |")
        L.append("|---|---|---|")
        for i, (_, r) in enumerate(imp_df[imp_df["模型"] == m].iterrows(), 1):
            L.append("| %d | %s | %.4f |" % (i, r["特征"], r["重要性"]))
        L.append("")
    L.append("## 五、结论与上线建议\n")
    L.append("1. **Logistic 回归 = 精度基线**：作为线性模型，它给出每个维度的权重方向，"
             "在本任务上 Accuracy/F1/AUC 均达到 %.4f 左右，说明 4 个门槛类特征本身判别力很强；"
             "它的价值在于\"可解释、可校准\"，作为基线衡量树模型究竟带来多少增益。" %
             base["Accuracy"])
    L.append("2. **随机森林 = 对比模型**：自动捕捉特征的非线性与交互（如\"城市满足 ∧ 技能命中\"的组合条件），"
             "无需标准化、对异常值不敏感，精度高于线性基线，训练仅需数秒。")
    if has_xgb_eval:
        xb = res_strict[res_strict["模型"].str.startswith("XGBoost")].iloc[0]
        L.append("3. **XGBoost = 最终上线模型**：梯度提升按残差逐轮修正、对阈值型特征（距离、学历序数差、经验区间、技能命中）"
                 "的切分最贴合业务规则，Accuracy %.4f / F1 %.4f / ROC-AUC %.4f%s，"
                 "且支持早停（严格划分下 best_iteration=%s）与模型序列化，推理速度快、便于服务化。"
                 % (xb["Accuracy"], xb["F1"], xb["ROC-AUC"],
                    "（严格划分下为最优）" if best["模型"].startswith("XGBoost") else "（与最优模型基本持平）",
                    meta.get("best_iteration_strict")))
    else:
        L.append("3. **XGBoost = 最终上线模型**：本次运行环境未安装 xgboost，该项指标缺失；"
                 "执行 `pip install xgboost` 后重跑本脚本即可补全。")
    L.append("4. **上线方式**：`models/xgboost_scoring_model.json`（全量 %d 条样本重训的最终模型）"
             "＋ `models/model_metadata.json`（含 12 个特征的顺序、指标、划分信息）。"
             "推理时按 `features` 顺序构造特征向量 → `predict_proba` 得到匹配概率 → 乘 100 映射为 0~100 分匹配得分。" % n_all)
    L.append("5. **使用建议**：对同一份简历批量给岗位打分后按分数排序即可得到推荐列表；"
             "生产环境建议把\"命中 ≥1 技能\"这类硬门槛放进召回阶段，模型分数用于精排。\n")
    L.append("> 说明：标签由 4 条业务规则生成，因此各模型都接近上限、差距被压缩；"
             "若后续引入人工标注样本或更难负样本（只差 1 项门槛的近似岗位），模型间差距会明显拉开。\n")
    L.append("## 六、输出文件\n")
    L.append("| 文件 | 说明 |")
    L.append("|---|---|")
    L.append("| `data/processed/模型评估结果.csv` | 严格划分下四模型指标 |")
    L.append("| `data/processed/模型评估结果_参考划分.csv` | 参考划分（岗位重叠）指标，用于对比泄漏影响 |")
    L.append("| `data/processed/模型特征重要性.csv` | XGBoost / 随机森林 特征重要性 |")
    L.append("| `models/xgboost_scoring_model.json` | **最终上线模型（XGBoost，全量重训）** |")
    L.append("| `models/model_metadata.json` | 模型元信息（特征顺序、指标、早停轮次、划分口径） |")
    L.append("| `reports/figures/模型对比_指标与耗时.png` 等 4 张图 | 指标对比、ROC、混淆矩阵、特征重要性 |")
    L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    main()
