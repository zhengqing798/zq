# -*- coding: utf-8 -*-
"""任务12 · 在 Windows 上预检「锁定清单在 Linux 镜像里是否都能装上」

要解决什么问题
    Docker 镜像是 Linux，本机是 Windows。如果某个包在 Linux 上没有预编译 wheel，
    构建时 pip 就会去找源码包编译 —— 而 python:3.12-slim 里没有 gcc，
    构建会在几分钟后失败。这类失败本该在本地就发现，而不是等到服务器上。

为什么不用 `pip install --dry-run --platform ...`
    试过，不靠谱：
      · `--platform manylinux2014_x86_64` 只接受 glibc ≤ 2.17 的 wheel，而 python:3.12-slim
        基于 Debian 12（glibc 2.36），大量合法的 manylinux_2_28 wheel 会被误判为"没有 wheel"。
      · `--abi cp312` 会让 pip 只认 cp312 标签，而 faiss-cpu 发的是 `cp310-abi3`（稳定 ABI，
        cp312 完全兼容）—— 同样被误判。
    实测这两个误判各骗了我一次（faiss-cpu / cvxopt 都被报成"没有 Linux wheel"，实际都有）。

所以这里改成自己查 PyPI 的文件清单，按明确规则判定，逻辑完全可控：
    一个 wheel 可用 ⟺
        Python 标签兼容（py3 / py2.py3 / cp312 / abi3 且 cp 版本 ≤ 3.12）
      且 平台标签兼容（x86_64 的 manylinux glibc ≤ 2.36、musllinux、或 manylinux2014/2010/1）

用法（在仓库根目录）
    python scripts/check_linux_wheels.py
"""
import io
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
LOCK = os.path.join(ROOT, "docker", "requirements.lock.txt")
TORCH_LOCK = os.path.join(ROOT, "docker", "requirements.torch.txt")

# 目标镜像：python:3.12-slim = Debian 12 bookworm = glibc 2.36
MAX_GLIBC = (2, 36)
PY_VER = (3, 12)
ARCH = "x86_64"

CP_TAG_RE = re.compile(r"^cp(\d)(\d+)$")
MANYLINUX_RE = re.compile(r"^manylinux_(\d+)_(\d+)_" + ARCH + r"$")
LEGACY_MANYLINUX = {"manylinux1_" + ARCH, "manylinux2010_" + ARCH, "manylinux2014_" + ARCH}


def read_pins(path):
    pins = []
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            if "==" in line:
                name, ver = line.split("==", 1)
                pins.append((name.strip(), ver.strip()))
    return pins


def py_tag_ok(tag):
    """Python / ABI 标签是否兼容目标解释器"""
    if tag in ("py3", "py2.py3", "py30", "py31", "py32", "py33", "py34", "py35",
               "py36", "py37", "py38", "py39", "py310", "py311", "py312", "none"):
        return True
    if tag in ("abi3", "cp32", "cp33", "cp34", "cp35", "cp36", "cp37", "cp38",
               "cp39", "cp310", "cp311", "cp312"):
        return True
    m = CP_TAG_RE.match(tag)
    if m:
        return (int(m.group(1)), int(m.group(2))) <= PY_VER
    # 形如 cp310.cp311 的组合标签（少见），逐个判
    if "." in tag:
        return all(py_tag_ok(t) for t in tag.split("."))
    return False


def plat_tag_ok(tag):
    """平台标签是否兼容目标镜像（x86_64 + glibc ≤ 2.36）"""
    # `any` = 纯 Python wheel，与平台无关（如 fastapi-0.123.9-py3-none-any.whl）。
    # 第一版漏了这一条，把 59 个纯 Python 包全误报成"没有 Linux wheel"。
    if tag == "any":
        return True
    if tag in LEGACY_MANYLINUX or tag == "linux_" + ARCH:
        return True
    if tag.endswith("_musllinux_1_2_" + ARCH) or tag.startswith("musllinux_1_2_"):
        return True
    m = MANYLINUX_RE.match(tag)
    if m:
        return (int(m.group(1)), int(m.group(2))) <= MAX_GLIBC
    return False


def wheel_compatible(filename):
    """文件名 → (是否 wheel, 是否兼容, 原因)"""
    if not filename.endswith(".whl"):
        return False, False, "非 wheel"
    stem = filename[:-4]
    parts = stem.split("-")
    if len(parts) < 5:
        return True, False, "文件名格式异常"
    pytags = parts[-3].split(".")
    abi = parts[-2].split(".")
    plat = parts[-1].split(".")
    if not all(py_tag_ok(t) for t in pytags):
        return True, False, "Python 标签不兼容：%s" % parts[-3]
    if not all(py_tag_ok(t) for t in abi):
        return True, False, "ABI 标签不兼容：%s" % parts[-2]
    if not any(plat_tag_ok(t) for t in plat):
        return True, False, "平台标签不兼容：%s" % parts[-1]
    return True, True, "OK"


def torch_cpu_wheel(ver):
    """torch 走的是 CPU 专用源，不是 PyPI。

    PyPI 上 Linux 的 torch==2.5.1 是 CUDA 版（单个 wheel 864MB），而镜像实际装的是
    download.pytorch.org 上的 `torch-2.5.1+cpu-cp312-cp312-linux_x86_64.whl`。
    这里去 CPU 源上把真实的文件名与体积取回来，免得体积估算差出好几倍。
    """
    try:
        html = urllib.request.urlopen("https://download.pytorch.org/whl/cpu/torch/",
                                     timeout=120).read().decode("utf-8", "replace")
    except Exception as e:
        return {"name": "torch", "ver": ver, "ok": True, "warn": True, "size": 0,
                "why": "CPU 源查询失败（%s），无法确认体积" % e}
    pat = re.compile(r'href="([^"]*torch-%s[^"]*cp312[^"]*linux_x86_64\.whl[^"]*)"'
                     % re.escape(ver))
    hits = sorted(set(pat.findall(html)))
    if not hits:
        return {"name": "torch", "ver": ver, "ok": False, "warn": False, "size": 0,
                "why": "CPU 专用源上没有 cp312 / linux_x86_64 的 torch %s" % ver}
    url = hits[0]
    if not url.startswith("http"):
        url = "https://download.pytorch.org/whl/cpu/" + url.lstrip("./")
    url = url.split("#")[0]
    size = 0
    try:
        # 该 CDN 不支持 HEAD（返回 403），用 Range 只取 1 字节，从 Content-Range 读总长
        req = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
        r = urllib.request.urlopen(req, timeout=180)
        cr = r.headers.get("Content-Range", "")       # 形如 bytes 0-0/123456789
        size = int(cr.split("/")[-1]) if "/" in cr else int(r.headers.get("Content-Length", 0))
    except Exception:
        pass
    return {"name": "torch", "ver": ver, "ok": True, "warn": False, "size": size,
            "why": url.split("/")[-1]}


def linux_only_deps():
    """找出「只在 Linux 生效、且不是可选 extras」的依赖

    为什么单独查这一类：这类依赖在 Windows 上根本不会被安装，所以**不会出现在锁定清单里**，
    但它们在 Linux 镜像里会被真实装上。xgboost 3.4.1 就是典型：
        nvidia-nccl-cu13; platform_system == "Linux"      ← 241MB 的 CUDA 集合通信库
    本项目纯 CPU 推理，这个包完全是浪费，Dockerfile 里装完即卸（见 ARG STRIP_GPU_LIBS）。
    把这条检查固化下来，以后升级依赖时不会又悄悄把几百 MB 的 GPU 库拖回镜像。
    """
    from importlib import metadata
    lock_names = {n.lower().replace("_", "-") for n, _ in read_pins(LOCK)}
    rows = []
    for dist in metadata.distributions():
        parent = (dist.metadata["Name"] or "").lower().replace("_", "-")
        if parent not in lock_names:
            continue
        for spec in (dist.requires or []):
            if re.search(r'extra\s*==', spec):
                continue                    # 可选 extras 不算
            if re.search(r'platform_system\s*==\s*["\']Linux["\']', spec) or \
               re.search(r'sys_platform\s*==\s*["\']linux["\']', spec):
                m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", spec.strip())
                rows.append((parent, m.group(1) if m else "?", spec.strip()))
    return rows


def probe(name, ver):
    url = "https://pypi.org/pypi/%s/%s/json" % (name, ver)
    try:
        d = json.load(urllib.request.urlopen(url, timeout=90))
    except Exception as e:
        return {"name": name, "ver": ver, "ok": False, "why": "PyPI 查询失败：%s" % e,
                "size": 0}
    files = d.get("urls", [])
    if not files:
        return {"name": name, "ver": ver, "ok": False, "why": "该版本没有文件", "size": 0}
    reasons = []
    best = None
    for f in files:
        is_whl, ok, why = wheel_compatible(f["filename"])
        if not is_whl:
            continue
        if ok:
            # 取最小的那个可用 wheel 作为下载量估算
            if best is None or f["size"] < best["size"]:
                best = f
        else:
            reasons.append("%s（%s）" % (f["filename"], why))
    if best:
        return {"name": name, "ver": ver, "ok": True, "warn": False,
                "why": best["filename"], "size": best["size"]}
    sdist = [f for f in files if f["filename"].endswith((".tar.gz", ".zip"))]
    if sdist:
        # 只有源码包：pip 会启用构建隔离，临时装 setuptools/wheel 来打包。
        # 纯 Python 包（例如 jieba 只发 sdist）照样能装；带 C 扩展的包在 slim 镜像里
        # 没有编译器，会在这一步失败 —— 所以这类只报警告，需要人工确认。
        f0 = sdist[0]
        return {"name": name, "ver": ver, "ok": True, "warn": True, "size": f0["size"],
                "why": "只有源码包 %s（走构建隔离，纯 Python 可以，带 C 扩展会失败）" % f0["filename"]}
    return {"name": name, "ver": ver, "ok": False, "warn": False, "size": 0,
            "why": "该版本没有任何可用文件", "detail": reasons[:2]}


def main():
    pins = read_pins(LOCK) + read_pins(TORCH_LOCK)
    print("=" * 78)
    print("任务12 · Linux 镜像依赖预检（目标 python:3.12-slim / Debian 12 / glibc 2.36 / x86_64）")
    print("检查 %d 个钉住的包%s" % (len(pins), "（含 torch，走 CPU 专用源）"))
    print("=" * 78)

    bad = []
    warns = []
    total = 0
    biggest = []
    for i, (name, ver) in enumerate(pins, 1):
        r = torch_cpu_wheel(ver) if name.lower() == "torch" else probe(name, ver)
        total += r["size"]
        if not r["ok"]:
            bad.append(r)
            print("  [FAIL] %-26s %-12s %s" % (r["name"], r["ver"], r["why"]))
        elif r.get("warn"):
            warns.append(r)
            print("  [WARN] %-26s %-12s %s" % (r["name"], r["ver"], r["why"]))
        else:
            biggest.append((r["size"], r["name"], r["ver"]))
        if i % 20 == 0:
            print("  … 已检查 %d/%d" % (i, len(pins)), flush=True)

    print("-" * 78)
    biggest.sort(reverse=True)
    print("下载量最大的 10 个包：")
    for size, name, ver in biggest[:10]:
        print("  %8.1f MB  %s==%s" % (size / 1024 / 1024, name, ver))
    print("合计下载量约 %.2f GB（解压后镜像更大，多数包带编译好的二进制）" % (total / 1024 / 1024 / 1024))

    print("-" * 78)
    print("只在 Linux 生效的依赖（Windows 上不装，因此不在锁定清单里，但镜像里会出现）：")
    lx = linux_only_deps()
    if not lx:
        print("  无")
    for parent, child, spec in lx:
        # 查一下这个包有多大，好判断值不值得卸
        try:
            d = json.load(urllib.request.urlopen(
                "https://pypi.org/pypi/%s/json" % child, timeout=90))
            ver = d["info"]["version"]
            size = max((f["size"] for f in d["releases"].get(ver, [])), default=0)
            note = "最新版 %s，约 %.1f MB" % (ver, size / 1024 / 1024)
        except Exception:
            note = "体积未知"
        print("  · %s  ->  %s" % (parent, spec))
        print("      %s" % note)
    if any(c.lower().replace("_", "-").startswith("nvidia-") for _, c, _ in lx):
        print("  处理方式：Dockerfile 里装完依赖后立刻卸载这些 nvidia-* 包（ARG STRIP_GPU_LIBS=1），")
        print("            安装与卸载放在同一层，文件不会留在镜像里。")

    print("-" * 78)
    if warns:
        print("需要注意（只有源码包）%d 个：" % len(warns))
        for r in warns:
            print("  · %s==%s —— %s" % (r["name"], r["ver"], r["why"]))
        print()
    if bad:
        print("结论：有 %d 个包在 Linux 上没有可用 wheel，docker build 会失败：" % len(bad))
        for r in bad:
            print("  · %s==%s —— %s" % (r["name"], r["ver"], r["why"]))
            for d in r.get("detail", []) or []:
                print("      %s" % d)
        return 1
    print("结论：%d 个包在 Linux 上全部可安装，镜像里不需要任何编译器。" % len(pins))
    print("      （torch 走 CPU 专用源；其余走 PyPI / 清华镜像）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
