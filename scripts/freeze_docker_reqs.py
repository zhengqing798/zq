# -*- coding: utf-8 -*-
"""任务12 · 生成 Docker 镜像的依赖锁定文件 `docker/requirements.lock.txt`

为什么需要这个脚本
    本地用 `requirements.txt`（写的是 `>=` 区间）跑通 189 项 pytest，不代表几周后
    服务器上构建出来的环境还是同一套 —— 某个包发新版就可能让镜像里的接口行为变化。
    容器化要求"本地验证过的环境"可复现，所以把当前解释器里**实际装到的版本**钉死。

为什么不能直接 `pip freeze`
    本机的全局 Python 环境里还装着一些与本项目无关的包（早期评估阶段留下的
    chromadb / nameko / eventlet / cvxopt 等）。直接 freeze 会有两个后果：
      · 镜像白白变大，还引入了根本没在跑的东西；
      · **构建会直接失败** —— 例如 cvxopt==1.3.3 在 Linux 上没有预编译 wheel，
        python:3.12-slim 里也没有编译器，`pip install` 会中断。
    所以这里改成：以 `requirements.txt` 里声明的依赖为起点，**递归求已安装依赖闭包**，
    只钉真正会被导入的那些包。

不钉的三类
    · pywin32 / WMI  —— Windows 专有，Linux 镜像里装不上
    · torch          —— 必须走 CPU 专用源；PyPI 上 Linux 的 torch 是 CUDA 版，
                        会多拖约 2.5GB 的 nvidia-* 依赖。单独放 requirements.torch.txt
    · pip / setuptools / wheel —— 基础镜像自带

用法（在仓库根目录）
    python scripts/freeze_docker_reqs.py
"""
import os
import re
import sys
from importlib import metadata

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REQ_TXT = os.path.join(ROOT, "requirements.txt")
OUT = os.path.join(ROOT, "docker", "requirements.lock.txt")

# 直接剔除（Windows 专有 + 单独安装的 torch + 打包工具）
EXCLUDE = {"pywin32", "wmi", "torch", "pip", "setuptools", "wheel"}

# 只取名字：去掉版本区间、环境标记、注释与 extras
NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def norm(name):
    """PEP 503 规范化：比较与去重都用小写加连字符"""
    return re.sub(r"[-_.]+", "-", name).lower()


def direct_requirements():
    """从 requirements.txt 里取出顶层依赖名（忽略注释、空行、-r/-i 等选项）"""
    names = []
    with open(REQ_TXT, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            m = NAME_RE.match(line)
            if m:
                names.append(m.group(1))
    return names


def installed_closure(roots):
    """从顶层依赖出发，递归收集"已安装"的依赖闭包

    只走**非 extras 依赖**（即 Requirements-Dist 里不带 `extra == "xxx"` 标记的那些）：
    extras 往往是平台相关的可选加速件（如 uvicorn 的 uvloop 在 Windows 上根本不装），
    把它们算进来会让锁定清单不可复现。容器里因此使用纯 uvicorn（见 docs/部署手册.md）。
    """
    closure = {}          # 规范化名 -> (显示名, 版本)
    missing = []
    queue = list(roots)
    seen = set()
    while queue:
        raw = queue.pop()
        key = norm(raw)
        if key in seen or key in EXCLUDE:
            continue
        seen.add(key)
        try:
            dist = metadata.distribution(raw)
        except metadata.PackageNotFoundError:
            missing.append(raw)
            continue
        closure[key] = (dist.metadata["Name"] or raw, dist.version)
        for spec in (dist.requires or []):
            if re.search(r'extra\s*==', spec):
                continue                       # 可选 extras，跳过
            m = NAME_RE.match(spec.strip())
            if m:
                queue.append(m.group(1))
    return closure, missing


HEADER = [
    "# -*- coding: utf-8 -*-",
    "# 任务12 · Docker 镜像依赖锁定（由 scripts/freeze_docker_reqs.py 自动生成，请勿手改）",
    "#",
    "# 生成方式：以 requirements.txt 里声明的顶层依赖为起点，递归求**已安装依赖闭包**，",
    "#           逐个钉住版本。这样做的原因见脚本注释：直接 pip freeze 会把无关包",
    "#           （chromadb / nameko / cvxopt 等）也带进镜像，其中 cvxopt 在 Linux 上没有",
    "#           预编译 wheel，会导致 docker build 直接失败。",
    "# 作用：镜像内装的版本与本地「189 项 pytest + 8 路由渲染检查全部通过」的环境完全一致。",
    "# 不含 torch：torch 走 CPU 专用源单独安装，见 docker/requirements.torch.txt。",
    "# 重新生成：python scripts/freeze_docker_reqs.py",
    "#",
    "# ⚠️ 第一行的 `coding: utf-8` 不能删：pip 只按 BOM / PEP 263 探测编码，两者都没有就退回",
    "#    系统区域编码；中文 Windows 是 GBK，会把下面这些中文注释解码失败并中断安装。",
    "",
]


def main():
    roots = direct_requirements()
    closure, missing = installed_closure(roots)

    lines = []
    for key in sorted(closure):
        name, ver = closure[key]
        lines.append("%s==%s" % (name, ver))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    # newline="\n"：强制 LF，避免 Windows 的 CRLF 混进镜像构建上下文
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(HEADER + lines) + "\n")

    print("顶层依赖 %d 个：%s" % (len(roots), ", ".join(roots)))
    print("已写入 %s" % OUT)
    print("  依赖闭包共钉住 %d 个包" % len(lines))
    print("  本机已安装但在闭包外（不进镜像）：")
    allinst = {norm(d.metadata["Name"]): d.version for d in metadata.distributions()
               if d.metadata["Name"]}
    outside = sorted(set(allinst) - set(closure) - EXCLUDE)
    print("    %d 个：%s" % (len(outside), ", ".join(outside[:40])
                             + (" …" if len(outside) > 40 else "")))
    if missing:
        # 不用 emoji：中文 Windows 控制台是 GBK，打印非 GBK 字符会 UnicodeEncodeError 崩掉
        print("  [警告] 声明了但本机没装（镜像里会缺包）：%s" % ", ".join(sorted(set(missing))))
    print("  解释器：%s" % sys.version.split()[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
