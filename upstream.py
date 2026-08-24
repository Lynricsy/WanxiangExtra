"""
上游构建工具链：把上游仓库的**代码**取下来在本地执行，而不是等它们发布产物。

- felixonmars/fcitx5-pinyin-zhwiki：提供 Makefile / convert.py / zhwiki-web-slang.py
- outloudvi/mw2fcitx（pkg-moegirl 分支）：提供萌百构建用的 fixfile.json 与补充词表

克隆一律使用浅克隆并强制同步到远端最新提交，保证每次构建都跟随上游代码。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Sequence

ZHWIKI_REPO = "https://github.com/felixonmars/fcitx5-pinyin-zhwiki.git"
ZHWIKI_BRANCH = "master"

MOEGIRL_REPO = "https://github.com/outloudvi/mw2fcitx.git"
MOEGIRL_BRANCH = "pkg-moegirl"


def run(
    cmd: Sequence[str],
    cwd: Optional[Path] = None,
    env: Optional[dict[str, str]] = None,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    """执行子进程并在失败时抛出 CalledProcessError。"""
    print(f"$ {' '.join(str(c) for c in cmd)}" + (f"  (cwd={cwd})" if cwd else ""))
    return subprocess.run(
        [str(c) for c in cmd],
        cwd=str(cwd) if cwd else None,
        env=env,
        check=True,
        capture_output=capture,
        text=capture,
    )


def script_env() -> dict[str, str]:
    """
    构造运行上游脚本的环境变量。

    上游脚本的 shebang 是 ``#!/usr/bin/env python3``，而依赖（opencc、regex、
    pypinyin…）装在当前解释器所在环境里。把当前解释器目录前置到 PATH，
    使 virtualenv 与 CI 两种场景下都能解析到正确的 python3。

    注意不能对 sys.executable 调用 resolve()：virtualenv 里的 python 是指向
    系统解释器的符号链接，解析后会直接指到 /usr/bin，反而丢掉虚拟环境。
    """
    env = dict(os.environ)
    bin_dir = str(Path(sys.executable).parent)
    env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
    return env


def sync_repo(url: str, branch: str, dest: Path) -> Path:
    """
    浅克隆或更新上游仓库到 ``dest``，返回工作副本路径。

    已存在的副本直接 fetch + reset --hard，避免每次构建重新下载；
    副本损坏（.git 缺失）时整体重建。
    """
    dest = dest.resolve()
    if (dest / ".git").is_dir():
        run(["git", "fetch", "--depth", "1", "origin", branch], cwd=dest)
        run(["git", "reset", "--hard", f"origin/{branch}"], cwd=dest)
        run(["git", "clean", "-fdx", "-e", "*.gz", "-e", "*-all-titles-in-ns0"], cwd=dest)
        return dest

    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            branch,
            url,
            str(dest),
        ]
    )
    return dest


def head_commit(repo: Path) -> str:
    """返回工作副本的 HEAD 短提交号，用于构建日志溯源。"""
    result = run(["git", "rev-parse", "--short", "HEAD"], cwd=repo, capture=True)
    return result.stdout.strip()
