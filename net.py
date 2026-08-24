"""
HTTP 小工具：统一 User-Agent 与流式下载。

Wikimedia 会按 User-Agent 拒绝请求（默认的 ``python-requests/x.y`` 直接 403），
其机器人策略要求带上可联系到项目的标识，因此这里集中定义一次，避免各处遗漏。
"""

from __future__ import annotations

from pathlib import Path

import requests

USER_AGENT = "WanxiangExtra/1.0 (+https://github.com/Lynricsy/WanxiangExtra)"

TIMEOUT = 60


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def download(url: str, dest: Path, session: requests.Session) -> None:
    """流式下载到本地文件，避免大文件一次性读入内存。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with session.get(url, stream=True, timeout=TIMEOUT) as resp:
        resp.raise_for_status()
        with dest.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                f.write(chunk)
