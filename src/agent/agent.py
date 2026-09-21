# -*- coding: utf-8 -*-
"""
任务10 · Agent 智能体（DeepSeek Function Calling + 工具编排 + 缓存 + 调用上限）

流程：用户问题 → LLM 决定调哪个工具 → 本地执行工具（RAG 检索/结构化筛选/人岗匹配/聚类画像）
      → 把工具结果回灌给 LLM → LLM 汇总成带来源的回答。最多 6 轮工具调用。

工程约束（防翻车）：
  · **缓存**：相同问题（同一 Prompt 版本）命中 `data/rag/agent_cache.json`，省 token 也保证演示可复现；
    缓存带 **写入时间**，超过 `CACHE_TTL_DAYS` 天自动失效重算；调用方可用 `use_cache=False` 强制真实调用
  · **多轮上下文**：`ask(question, history=[...])` 可以把最近几轮对话带上，追问（"那再列几个"）才能接续
  · **调用上限**：单次对话最多 6 轮工具调用、最多 12 次工具执行，超限就带着现有信息作答
  · **超时与重试**：单次请求 90s 超时；网络错误重试 2 次
  · **失败如实返回**：工具失败会把 `ok=false` 与错误信息交给模型，模型被要求直说没查到

运行：python src/agent/agent.py --ask "厦门有哪些 Java 岗位？"
"""
import argparse
import json
import os
import sys
import time

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
from prompts import PROMPT_VERSION, SYSTEM_PROMPT          # noqa: E402
from tools import TOOLS, call_tool                          # noqa: E402

# 缓存与调用日志的落盘位置。
# 本地默认写仓库内的 data/rag/；容器化部署（任务12）时由环境变量指到挂卷 /app/var 下 ——
# 镜像里的 data/ 是只读资产层，运行期数据不该写进去（重建容器就会丢）。
CACHE_PATH = os.environ.get("AGENT_CACHE",
                            os.path.join(ROOT, "data", "rag", "agent_cache.json"))
LOG_PATH = os.environ.get("AGENT_LOG",
                          os.path.join(ROOT, "data", "rag", "agent_calls.jsonl"))
MAX_ROUNDS = 6
MAX_TOOL_CALLS = 12
TIMEOUT = 90
MAX_TOKENS = 2000            # 回答更长不再被截断（v6 起 1200 → 2000）
TOOL_PAYLOAD_CHARS = 10000   # 回灌给模型的工具结果上限（v6 起 6000 → 10000）
CACHE_TTL_DAYS = 7           # 缓存有效期：超过就重新真实调用
MAX_HISTORY_TURNS = 6        # 最多带几轮上下文


def load_env():
    """读取大模型配置：**环境变量优先，`.env` 文件兜底**。

    顺序不能反，容器化部署（任务12）就卡在这里：
      · docker compose 用 `env_file` 把宿主机的 `.env` 注入成容器内的**环境变量**，
        镜像里根本不存在 `.env` 文件 —— 若这里只读文件，容器里会直接报"缺少 API Key"；
      · 本地开发保持原样：只放一个 `.env` 文件即可，行为与之前完全一致；
      · 两者同时存在时环境变量胜出（12-Factor：配置属于运行环境，不属于代码目录）。
    """
    env = {}
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    for k in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


class Agent:
    def __init__(self, verbose=True):
        env = load_env()
        if "DEEPSEEK_API_KEY" not in env:
            raise SystemExit("缺少 .env 里的 DEEPSEEK_API_KEY")
        self.key = env["DEEPSEEK_API_KEY"]
        self.base = env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
        self.model = env.get("DEEPSEEK_MODEL", "deepseek-flash")
        self.verbose = verbose
        self.cache = json.load(open(CACHE_PATH, encoding="utf-8")) if os.path.exists(CACHE_PATH) else {}

    # ---------------- 底层请求 ----------------
    def _chat(self, messages):
        last = None
        for attempt in range(3):
            try:
                r = requests.post(self.base + "/chat/completions",
                                  headers={"Authorization": "Bearer " + self.key,
                                           "Content-Type": "application/json"},
                                  json={"model": self.model, "messages": messages,
                                        "tools": TOOLS, "tool_choice": "auto",
                                        "temperature": 0, "max_tokens": MAX_TOKENS},
                                  timeout=TIMEOUT)
                if r.status_code == 200:
                    return r.json()
                last = "HTTP %d: %s" % (r.status_code, r.text[:200])
            except Exception as e:
                last = "%s: %s" % (type(e).__name__, e)
            time.sleep(2 * (attempt + 1))
        raise RuntimeError("DeepSeek 调用失败：" + str(last))

    # ---------------- 缓存 ----------------
    @staticmethod
    def _age_seconds(rec):
        """缓存年龄（秒）；无法判断时间就返回 None（按过期处理）

        注意：`cached_at` 是**给人看的时间字符串**，不能用它做减法——
        这里只认数值型时间戳（`cached_ts` / `asked_at`），字符串则解析后回退。
        （第一版就是拿 cached_at 直接 `time.time() - ts`，命中缓存时必抛
        TypeError: unsupported operand type(s) for -: 'float' and 'str'）
        """
        for k in ("cached_ts", "asked_at"):
            try:
                return time.time() - float(rec.get(k))
            except (TypeError, ValueError):
                continue
        v = rec.get("cached_at")
        if isinstance(v, str) and v:
            try:
                return time.time() - time.mktime(time.strptime(v, "%Y-%m-%d %H:%M:%S"))
            except ValueError:
                pass
        return None

    def _cache_get(self, key):
        """命中且未过期才返回；过期/时间不可辨的条目顺手丢掉"""
        rec = self.cache.get(key)
        if not rec:
            return None
        age = self._age_seconds(rec)
        if age is None or age > CACHE_TTL_DAYS * 86400:
            self.cache.pop(key, None)
            return None
        out = dict(rec)
        out["cached"] = True
        out["cache_age_hours"] = round(age / 3600, 1)
        return out

    def _cache_put(self, key, rec):
        self.cache[key] = rec
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        json.dump(self.cache, open(CACHE_PATH, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

    # ---------------- 主流程 ----------------
    def ask(self, question, use_cache=True, history=None):
        """history: [{"role": "user"/"assistant", "content": "..."}] 最近几轮对话（可选）"""
        ck = "%s|%s|%s" % (PROMPT_VERSION, self.model, question.strip())
        if use_cache:
            hit = self._cache_get(ck)
            if hit:
                return hit
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for h in (history or [])[-MAX_HISTORY_TURNS * 2:]:
            role = "assistant" if h.get("role") == "assistant" else "user"
            text = str(h.get("content") or "").strip()
            if text:
                messages.append({"role": role, "content": text[:2000]})
        messages.append({"role": "user", "content": question})
        tool_log, tokens = [], {"prompt": 0, "completion": 0}
        t0 = time.time()
        n_tools = 0
        for rnd in range(MAX_ROUNDS):
            data = self._chat(messages)
            u = data.get("usage") or {}
            tokens["prompt"] += u.get("prompt_tokens", 0)
            tokens["completion"] += u.get("completion_tokens", 0)
            msg = data["choices"][0]["message"]
            calls = msg.get("tool_calls") or []
            if not calls:
                answer = (msg.get("content") or "").strip()
                break
            messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
            for c in calls:
                if n_tools >= MAX_TOOL_CALLS:
                    messages.append({"role": "tool", "tool_call_id": c["id"],
                                     "content": json.dumps({"ok": False, "summary": "工具调用已达上限，请基于已有信息作答"},
                                                           ensure_ascii=False)})
                    continue
                n_tools += 1
                name = c["function"]["name"]
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                res = call_tool(name, args)
                payload = res.get("data")
                ids, nms = [], []
                if isinstance(payload, list):
                    for d in payload:
                        if isinstance(d, dict):
                            if d.get("岗位ID"):
                                ids.append(d["岗位ID"])
                            if d.get("岗位名称") or d.get("簇名"):
                                nms.append(d.get("岗位名称") or d.get("簇名"))
                tool_log.append({"工具": name, "参数": args, "结果摘要": res.get("summary"),
                                 "ok": res.get("ok"), "来源": res.get("来源") or [],
                                 "岗位样本": ids[:5], "名称样本": nms[:3]})
                if self.verbose:
                    print("   [轮 %d] 调用 %s(%s) → %s" %
                          (rnd + 1, name, json.dumps(args, ensure_ascii=False)[:80], res.get("summary")), flush=True)
                messages.append({"role": "tool", "tool_call_id": c["id"],
                                 "content": json.dumps(res, ensure_ascii=False)[:TOOL_PAYLOAD_CHARS]})
        else:
            answer = "（达到工具调用轮数上限，以下为已有信息）"
        rec = {"question": question, "answer": answer, "tools": tool_log, "rounds": rnd + 1,
               "tokens": tokens, "seconds": round(time.time() - t0, 1),
               "prompt_version": PROMPT_VERSION, "model": self.model, "cached": False,
               "cached_ts": time.time(),
               "cached_at": time.strftime("%Y-%m-%d %H:%M:%S"),
               "history_turns": len(history or []) // 2}
        if use_cache:
            self._cache_put(ck, rec)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec


def main():
    ap = argparse.ArgumentParser(description="Agent 命令行入口")
    ap.add_argument("--ask", help="单次提问")
    ap.add_argument("--no-cache", action="store_true", help="忽略缓存，强制真实调用")
    ap.add_argument("--repl", action="store_true", help="交互模式（带上下文）")
    a = ap.parse_args()
    ag = Agent()
    print("模型 %s ｜ Prompt %s ｜ 工具 %d 个 ｜ 缓存 TTL %d 天" %
          (ag.model, PROMPT_VERSION, len(TOOLS), CACHE_TTL_DAYS))
    if a.ask:
        r = ag.ask(a.ask, use_cache=not a.no_cache)
        print("\n【回答】%s\n\n（工具 %d 次 ｜ %d 轮 ｜ %.1fs ｜ tokens %s ｜ 缓存命中：%s）" %
              (r["answer"], len(r["tools"]), r["rounds"], r["seconds"], r["tokens"], r["cached"]))
        return
    print("输入问题（空行退出）：")
    hist = []
    while True:
        try:
            q = input("\n> ").strip()
        except EOFError:
            break
        if not q:
            break
        r = ag.ask(q, history=hist)
        print("\n【回答】%s" % r["answer"])
        print("（工具 %d 次 ｜ %.1fs ｜ tokens %s ｜ 缓存命中：%s）" %
              (len(r["tools"]), r["seconds"], r["tokens"], r["cached"]))
        hist += [{"role": "user", "content": q}, {"role": "assistant", "content": r["answer"]}]


if __name__ == "__main__":
    main()
