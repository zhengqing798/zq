# -*- coding: utf-8 -*-
"""
任务10 · Agent 智能体（DeepSeek Function Calling + 工具编排 + 缓存 + 调用上限）

流程：用户问题 → LLM 决定调哪个工具 → 本地执行工具（RAG 检索/结构化筛选/人岗匹配/聚类画像）
      → 把工具结果回灌给 LLM → LLM 汇总成带来源的回答。最多 6 轮工具调用。

工程约束（防翻车）：
  · **缓存**：相同问题（同一 Prompt 版本）直接命中 `data/rag/agent_cache.json`，省 token 也保证演示可复现
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

CACHE_PATH = os.path.join(ROOT, "data", "rag", "agent_cache.json")
LOG_PATH = os.path.join(ROOT, "data", "rag", "agent_calls.jsonl")
MAX_ROUNDS = 6
MAX_TOOL_CALLS = 12
TIMEOUT = 90


def load_env():
    env = {}
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
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
                                        "temperature": 0, "max_tokens": 1200},
                                  timeout=TIMEOUT)
                if r.status_code == 200:
                    return r.json()
                last = "HTTP %d: %s" % (r.status_code, r.text[:200])
            except Exception as e:
                last = "%s: %s" % (type(e).__name__, e)
            time.sleep(2 * (attempt + 1))
        raise RuntimeError("DeepSeek 调用失败：" + str(last))

    # ---------------- 主流程 ----------------
    def ask(self, question, use_cache=True):
        ck = "%s|%s|%s" % (PROMPT_VERSION, self.model, question.strip())
        if use_cache and ck in self.cache:
            rec = self.cache[ck]
            rec["cached"] = True
            return rec
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": question}]
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
                tool_log.append({"工具": name, "参数": args, "结果摘要": res.get("summary"),
                                 "ok": res.get("ok")})
                if self.verbose:
                    print("   [轮 %d] 调用 %s(%s) → %s" %
                          (rnd + 1, name, json.dumps(args, ensure_ascii=False)[:80], res.get("summary")), flush=True)
                messages.append({"role": "tool", "tool_call_id": c["id"],
                                 "content": json.dumps(res, ensure_ascii=False)[:6000]})
        else:
            answer = "（达到工具调用轮数上限，以下为已有信息）"
        rec = {"question": question, "answer": answer, "tools": tool_log, "rounds": rnd + 1,
               "tokens": tokens, "seconds": round(time.time() - t0, 1),
               "prompt_version": PROMPT_VERSION, "model": self.model, "cached": False}
        if use_cache:
            self.cache[ck] = rec
            os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
            json.dump(self.cache, open(CACHE_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec


def main():
    ap = argparse.ArgumentParser(description="Agent 命令行入口")
    ap.add_argument("--ask", help="单次提问")
    ap.add_argument("--no-cache", action="store_true", help="忽略缓存")
    ap.add_argument("--repl", action="store_true", help="交互模式")
    a = ap.parse_args()
    ag = Agent()
    print("模型 %s ｜ Prompt %s ｜ 工具 %d 个" % (ag.model, PROMPT_VERSION, len(TOOLS)))
    if a.ask:
        r = ag.ask(a.ask, use_cache=not a.no_cache)
        print("\n【回答】%s\n\n（工具 %d 次 ｜ %d 轮 ｜ %.1fs ｜ tokens %s ｜ 缓存命中：%s）" %
              (r["answer"], len(r["tools"]), r["rounds"], r["seconds"], r["tokens"], r["cached"]))
        return
    print("输入问题（空行退出）：")
    while True:
        try:
            q = input("\n> ").strip()
        except EOFError:
            break
        if not q:
            break
        r = ag.ask(q)
        print("\n【回答】%s" % r["answer"])
        print("（工具 %d 次 ｜ %.1fs ｜ 缓存命中：%s）" % (len(r["tools"]), r["seconds"], r["cached"]))


if __name__ == "__main__":
    main()
