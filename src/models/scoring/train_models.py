# -*- coding: utf-8 -*-
"""
任务5 · 步骤4：训练匹配评分模型

任务与口径：
  · T1 回归：预测 `总分(0-100)`（MAE / RMSE / R² / MedAE）
  · T2 二分类：预测 `是否匹配`（`总分(0-100) ≥ 65`）（PR-AUC / ROC-AUC / P@10 / R@10 / MRR@10 / NDCG@10）
  · 划分口径：主口径「按简历」+ 对照口径「按岗位」，均 70/15/15（步骤3 已落盘，**不带 test 做任何选择**）
  · 三组对照实验：
      ① 全特征 + 纯净标签（`总分_规则`）—— 特征充分性上界，仅 T1
      ② 全特征 + 噪声标签（`总分(0-100)`）—— **主结果**，T1 + T2
      ③ 仅 3 个文本相似度特征（标签未使用的信息）—— 衡量"抛开规则、纯语义"的能力，T1 + T2
  · 模型：线性基线 / SVR(RBF) / 随机森林 / XGBoost；分类为 逻辑回归 / LinearSVC / 随机森林 / XGBoost
  · 调参只在 `valid` 上做，且为省时在 train 的 6 万行子样本上调参一次、跨实验复用（脚本内记录）
  · SVR 在 14.5 万行上训练代价过高，按 2 万行子样本训练（脚本内记录）

输出：
  · `data/processed/模型评估结果_回归.csv` / `模型评估结果_分类.csv`
  · `data/processed/模型调参记录.csv`（写入前先把上一版另存为 `模型调参记录_上一版.csv`，不覆盖历史）
  · `data/processed/模型特征重要性.csv`
  · `models/*.joblib`（每个口径×任务的最优模型，compress=3）+ `models/模型元数据.json`

运行：python src/models/scoring/train_models.py
"""
import json
import os
import sys
import time

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (average_precision_score, mean_absolute_error, mean_squared_error,
                             median_absolute_error, r2_score, roc_auc_score)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR, LinearSVC

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
P = os.path.join(ROOT, "data", "processed")
MODELS = os.path.join(ROOT, "models")
FEAT_CSV = os.path.join(P, "匹配特征_全量样本.csv")
COLS_CSV = os.path.join(P, "匹配特征_列清单.csv")
SPLITS = {"按简历": os.path.join(P, "匹配样本_划分_按简历.csv"),
          "按岗位": os.path.join(P, "匹配样本_划分_按岗位.csv")}
OUT_REG = os.path.join(P, "模型评估结果_回归.csv")
OUT_CLS = os.path.join(P, "模型评估结果_分类.csv")
OUT_TUNE = os.path.join(P, "模型调参记录.csv")
OUT_TUNE_OLD = os.path.join(P, "模型调参记录_上一版.csv")
OUT_IMP = os.path.join(P, "模型特征重要性.csv")
OUT_META = os.path.join(MODELS, "模型元数据.json")

SEED = 42
TUNE_SUB = 60000          # 调参用子样本
SVR_SUB = 20000           # SVR 训练用子样本
TEXT_FEATS = ["岗位名称与期望岗位相似度", "描述与简历文本相似度", "描述与技能特长相似度"]
THRESHOLD = 65


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


# ------------------------------------------------------------------ 指标

def reg_metrics(y, p):
    return {"MAE": round(mean_absolute_error(y, p), 4),
            "RMSE": round(mean_squared_error(y, p) ** 0.5, 4),
            "R2": round(r2_score(y, p), 4),
            "MedAE": round(median_absolute_error(y, p), 4)}


def ranking_metrics(df, ycol, scol, k=10):
    """按简历分组排序，计算 P@10 / R@10 / MRR@10 / NDCG@10（推荐质量）"""
    ps, rs, mrrs, ndcgs = [], [], [], []
    disc = 1.0 / np.log2(np.arange(2, k + 2))
    for _, g in df.groupby("简历ID", sort=False):
        y = g[ycol].to_numpy(dtype=float)
        s = g[scol].to_numpy(dtype=float)
        n_pos = y.sum()
        if n_pos == 0:
            continue
        order = np.argsort(-s)
        top = order[:k]
        hits = y[top]
        ps.append(hits.sum() / min(k, len(top)))
        rs.append(hits.sum() / n_pos)
        pos_rank = np.where(y[order] > 0)[0]
        mrrs.append(1.0 / (pos_rank[0] + 1) if len(pos_rank) else 0.0)
        dcg = float((hits * disc[:len(hits)]).sum())
        ideal = float((np.sort(y)[::-1][:k] * disc[:min(k, len(y))]).sum())
        ndcgs.append(dcg / ideal if ideal > 0 else 0.0)
    return {"P@10": round(float(np.mean(ps)), 4), "R@10": round(float(np.mean(rs)), 4),
            "MRR@10": round(float(np.mean(mrrs)), 4), "NDCG@10": round(float(np.mean(ndcgs)), 4),
            "评估简历数": len(ps)}


# ------------------------------------------------------------------ 模型

def tune(param_grid, build_fn, Xtr, ytr, Xva, yva, metric, higher_better, log_rows, tag):
    best, best_score, best_params = None, None, None
    for params in param_grid:
        t0 = time.time()
        m = build_fn(params)
        m.fit(Xtr, ytr)
        p = m.predict(Xva)
        sc = metric(yva, p)
        log_rows.append({"阶段": "调参", "配置": tag, "参数": json.dumps(params, ensure_ascii=False),
                         "验证集指标": round(float(sc), 4), "耗时秒": round(time.time() - t0, 1)})
        log("    调参 %s %s → %.4f（%.0fs）" % (tag, params, sc, time.time() - t0))
        if best_score is None or (sc > best_score if higher_better else sc < best_score):
            best, best_score, best_params = m, sc, params
    return best_params, best_score


def main():
    os.makedirs(MODELS, exist_ok=True)
    feat = pd.read_csv(FEAT_CSV, encoding="utf-8-sig")
    cols = pd.read_csv(COLS_CSV, encoding="utf-8-sig")
    feats = cols.loc[cols["类型"] == "特征", "列名"].tolist()
    log("特征表 %s ｜ 特征 %d 个 ｜ 文本特征 %d 个" % (feat.shape, len(feats), len(TEXT_FEATS)))

    tune_rows, reg_rows, cls_rows, imp_rows, meta = [], [], [], [], {}

    for crit, sp_path in SPLITS.items():
        sp = pd.read_csv(sp_path, encoding="utf-8-sig")
        df = feat.merge(sp, on=["简历ID", "岗位ID"], how="left", validate="one_to_one")
        assert df["数据集"].notna().all()
        tr = df[df["数据集"] == "train"]
        va = df[df["数据集"] == "valid"]
        te = df[df["数据集"] == "test"]
        log("=== 口径 %s === train %d / valid %d / test %d" % (crit, len(tr), len(va), len(te)))

        sub = tr.sample(n=min(TUNE_SUB, len(tr)), random_state=SEED)
        svr_sub = tr.sample(n=min(SVR_SUB, len(tr)), random_state=SEED)

        # ---------- 调参（在子样本上，跨实验复用） ----------
        log("  调参（T1 回归）…")
        rf_best, _ = tune([{"max_depth": d} for d in (8, 16, None)],
                          lambda p: RandomForestRegressor(n_estimators=150, min_samples_leaf=1,
                                                          random_state=SEED, n_jobs=-1, **p),
                          sub[feats], sub["总分(0-100)"], va[feats], va["总分(0-100)"],
                          mean_absolute_error, False, tune_rows, "T1_RF_%s" % crit)
        xgb_best, _ = tune([{"learning_rate": lr} for lr in (0.05, 0.1)],
                           lambda p: xgb.XGBRegressor(n_estimators=300, max_depth=6, subsample=0.8,
                                                      colsample_bytree=0.8, tree_method="hist",
                                                      random_state=SEED, n_jobs=-1, verbosity=0, **p),
                           sub[feats], sub["总分(0-100)"], va[feats], va["总分(0-100)"],
                           mean_absolute_error, False, tune_rows, "T1_XGB_%s" % crit)
        log("  调参（T2 分类）…")
        rfc_best, _ = tune([{"max_depth": d} for d in (8, 16, None)],
                           lambda p: RandomForestClassifier(n_estimators=150, min_samples_leaf=1,
                                                            class_weight="balanced_subsample",
                                                            random_state=SEED, n_jobs=-1, **p),
                           sub[feats], sub["是否匹配"], va[feats], va["是否匹配"],
                           average_precision_score, True, tune_rows, "T2_RF_%s" % crit)
        xgbc_best, _ = tune([{"learning_rate": lr} for lr in (0.05, 0.1)],
                            lambda p: xgb.XGBClassifier(n_estimators=300, max_depth=6, subsample=0.8,
                                                        colsample_bytree=0.8, tree_method="hist",
                                                        scale_pos_weight=float((sub["是否匹配"] == 0).sum() /
                                                                               max((sub["是否匹配"] == 1).sum(), 1)),
                                                        random_state=SEED, n_jobs=-1, verbosity=0, **p),
                            sub[feats], sub["是否匹配"], va[feats], va["是否匹配"],
                            average_precision_score, True, tune_rows, "T2_XGB_%s" % crit)
        best_params = {"T1_RF": rf_best, "T1_XGB": xgb_best, "T2_RF": rfc_best, "T2_XGB": xgbc_best}
        meta.setdefault(crit, {})["最优超参数"] = best_params

        pos_w = float((tr["是否匹配"] == 0).sum() / max((tr["是否匹配"] == 1).sum(), 1))

        # ---------- 三组实验 ----------
        experiments = [
            ("①全特征+纯净标签", feats, "总分_规则", None),
            ("②全特征+噪声标签", feats, "总分(0-100)", "是否匹配"),
            ("③仅文本相似度特征", TEXT_FEATS, "总分(0-100)", "是否匹配"),
        ]
        for exp_name, cols_use, ycol, ccol in experiments:
            log("  --- %s（%d 特征）---" % (exp_name, len(cols_use)))
            # ===== T1 回归 =====
            reg_specs = [
                ("均值基线", lambda: DummyRegressor(strategy="mean"), tr, ycol),
                ("线性回归", lambda: make_pipeline(StandardScaler(), LinearRegression()), tr, ycol),
                ("SVR", lambda: make_pipeline(StandardScaler(),
                                              SVR(kernel="rbf", C=10.0, epsilon=1.0, gamma="scale")),
                 svr_sub, ycol),
                ("随机森林", lambda: RandomForestRegressor(n_estimators=150, min_samples_leaf=1,
                                                          random_state=SEED, n_jobs=-1,
                                                          **best_params["T1_RF"]), tr, ycol),
                ("XGBoost", lambda: xgb.XGBRegressor(n_estimators=300, max_depth=6, subsample=0.8,
                                                     colsample_bytree=0.8, tree_method="hist",
                                                     random_state=SEED, n_jobs=-1, verbosity=0,
                                                     **best_params["T1_XGB"]), tr, ycol),
            ]
            for mname, build, fit_df, target in reg_specs:
                t0 = time.time()
                m = build()
                m.fit(fit_df[cols_use], fit_df[target])
                row = {"口径": crit, "实验": exp_name, "模型": mname,
                       "训练行数": len(fit_df), "特征数": len(cols_use)}
                for nm, part in (("验证集", va), ("测试集", te)):
                    p = m.predict(part[cols_use])
                    row.update({"%s_%s" % (nm, k): v for k, v in reg_metrics(part[target], p).items()})
                row["耗时秒"] = round(time.time() - t0, 1)
                reg_rows.append(row)
                log("    T1 %-8s valid MAE %.3f ｜ test MAE %.3f ｜ %.0fs" %
                    (mname, row["验证集_MAE"], row["测试集_MAE"], row["耗时秒"]))
                est = getattr(m, "named_steps", {}).get("randomforestregressor") or \
                      getattr(m, "named_steps", {}).get("xgboostregressor") or \
                      (m if hasattr(m, "feature_importances_") else None)
                if est is not None and hasattr(est, "feature_importances_"):
                    for f, w in zip(cols_use, est.feature_importances_):
                        imp_rows.append({"口径": crit, "任务": "T1回归", "实验": exp_name, "模型": mname,
                                         "特征": f, "重要性": round(float(w), 5)})
                if crit and mname not in ("均值基线",) and exp_name == "②全特征+噪声标签":
                    meta.setdefault(crit, {}).setdefault("T1候选", {})[mname] = {
                        "valid_MAE": row["验证集_MAE"], "test_MAE": row["测试集_MAE"],
                        "fitted_on": len(fit_df)}
                    joblib.dump(m, os.path.join(MODELS, "_tmp_%s_T1_%s.joblib" % (crit, mname)), compress=3)

            if ccol is None:
                continue
            # ===== T2 二分类 =====
            cls_specs = [
                ("随机基线", lambda: DummyClassifier(strategy="prior")),
                ("逻辑回归", lambda: make_pipeline(StandardScaler(),
                                                   LogisticRegression(max_iter=2000, class_weight="balanced",
                                                                      random_state=SEED))),
                ("LinearSVC", lambda: make_pipeline(StandardScaler(),
                                                    LinearSVC(class_weight="balanced", random_state=SEED))),
                ("随机森林", lambda: RandomForestClassifier(n_estimators=150, min_samples_leaf=1,
                                                           class_weight="balanced_subsample",
                                                           random_state=SEED, n_jobs=-1,
                                                           **best_params["T2_RF"])),
                ("XGBoost", lambda: xgb.XGBClassifier(n_estimators=300, max_depth=6, subsample=0.8,
                                                      colsample_bytree=0.8, tree_method="hist",
                                                      scale_pos_weight=pos_w,
                                                      random_state=SEED, n_jobs=-1, verbosity=0,
                                                      **best_params["T2_XGB"])),
            ]
            for mname, build in cls_specs:
                t0 = time.time()
                m = build()
                m.fit(tr[cols_use], tr[ccol])
                row = {"口径": crit, "实验": exp_name, "模型": mname,
                       "训练行数": len(tr), "特征数": len(cols_use)}
                for nm, part in (("验证集", va), ("测试集", te)):
                    if hasattr(m, "predict_proba"):
                        s = m.predict_proba(part[cols_use])[:, 1]
                    else:                                   # LinearSVC：用决策值排序（单调等价）
                        s = m.decision_function(part[cols_use])
                    y = part[ccol].to_numpy()
                    tmp = part[["简历ID"]].copy()
                    tmp["_y"], tmp["_s"] = y, s
                    met = {"PR_AUC": round(average_precision_score(y, s), 4),
                           "ROC_AUC": round(roc_auc_score(y, s), 4)}
                    met.update(ranking_metrics(tmp, "_y", "_s"))
                    row.update({"%s_%s" % (nm, k): v for k, v in met.items()})
                row["耗时秒"] = round(time.time() - t0, 1)
                cls_rows.append(row)
                log("    T2 %-8s valid PR-AUC %.4f ｜ test PR-AUC %.4f ｜ test NDCG@10 %.4f ｜ %.0fs" %
                    (mname, row["验证集_PR_AUC"], row["测试集_PR_AUC"], row["测试集_NDCG@10"], row["耗时秒"]))
                est = getattr(m, "named_steps", {}).get("randomforestclassifier") or \
                      getattr(m, "named_steps", {}).get("xgboostclassifier") or \
                      (m if hasattr(m, "feature_importances_") else None)
                if est is not None and hasattr(est, "feature_importances_"):
                    for f, w in zip(cols_use, est.feature_importances_):
                        imp_rows.append({"口径": crit, "任务": "T2分类", "实验": exp_name, "模型": mname,
                                         "特征": f, "重要性": round(float(w), 5)})
                if mname not in ("随机基线",) and exp_name == "②全特征+噪声标签":
                    meta.setdefault(crit, {}).setdefault("T2候选", {})[mname] = {
                        "valid_PR_AUC": row["验证集_PR_AUC"], "test_PR_AUC": row["测试集_PR_AUC"]}
                    joblib.dump(m, os.path.join(MODELS, "_tmp_%s_T2_%s.joblib" % (crit, mname)), compress=3)

    # ---------- 落盘 ----------
    pd.DataFrame(reg_rows).to_csv(OUT_REG, index=False, encoding="utf-8-sig")
    pd.DataFrame(cls_rows).to_csv(OUT_CLS, index=False, encoding="utf-8-sig")
    pd.DataFrame(imp_rows).to_csv(OUT_IMP, index=False, encoding="utf-8-sig")
    if os.path.exists(OUT_TUNE) and not os.path.exists(OUT_TUNE_OLD):
        os.replace(OUT_TUNE, OUT_TUNE_OLD)
    pd.DataFrame(tune_rows).to_csv(OUT_TUNE, index=False, encoding="utf-8-sig")
    log("输出：模型评估结果_回归.csv（%d 行）、模型评估结果_分类.csv（%d 行）、模型特征重要性.csv（%d 行）、模型调参记录.csv（%d 行）"
        % (len(reg_rows), len(cls_rows), len(imp_rows), len(tune_rows)))

    # ---------- 选出各口径×任务的最优模型（**按验证集**选择，不看测试集） ----------
    for crit in SPLITS:
        for task, metric, higher, tmp_prefix in (("T1回归", "验证集_MAE", False, "T1"),
                                                 ("T2分类", "验证集_PR_AUC", True, "T2")):
            cands = meta.get(crit, {}).get("%s候选" % tmp_prefix, {})
            if not cands:
                continue
            key = "valid_MAE" if tmp_prefix == "T1" else "valid_PR_AUC"
            best = sorted(cands.items(), key=lambda kv: kv[1][key], reverse=higher)[0][0]
            src = os.path.join(MODELS, "_tmp_%s_%s_%s.joblib" % (crit, tmp_prefix, best))
            dst = os.path.join(MODELS, "%s_%s_best_%s.joblib" % (crit, task, best))
            if os.path.exists(src):
                os.replace(src, dst)
                meta[crit].setdefault("最优模型", {})[task] = {"模型": best, "文件": os.path.basename(dst),
                                                              "选择依据": key, "验证集指标": cands[best][key]}
                log("最优模型（%s / %s）：%s（%s=%.4f）" % (crit, task, best, key, cands[best][key]))
    for f in os.listdir(MODELS):                        # 清掉未被选中的临时模型
        if f.startswith("_tmp_"):
            os.remove(os.path.join(MODELS, f))
    meta["特征列表"] = {"全部特征": feats, "文本相似度特征": TEXT_FEATS}
    meta["说明"] = {
        "标签": "步骤1 规则加权得分（0–100），含 10% 噪声",
        "二分类阈值": THRESHOLD, "随机种子": SEED,
        "调参": "在 train 的 %d 行子样本上调参一次，跨实验复用；只在 valid 上评估" % TUNE_SUB,
        "SVR": "在 %d 行子样本上训练（全量训练代价过高）" % SVR_SUB,
        "模型选择": "每个口径×任务按验证集指标选最优（T1 看 MAE 最小，T2 看 PR-AUC 最大），测试集不参与选择",
    }
    with open(OUT_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    log("输出：models/模型元数据.json ｜ 模型文件 %d 个" % len([f for f in os.listdir(MODELS) if f.endswith('.joblib')]))


if __name__ == "__main__":
    main()
