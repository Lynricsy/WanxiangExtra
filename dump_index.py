"""
Wikimedia 转储索引：自行发现最新可用的 ``all-titles-in-ns0`` 转储。

上游 fcitx5-pinyin-zhwiki 的 Makefile 把转储日期硬编码为 ``VERSION=``，
只有维护者手动改动并发版后，词库才会更新。本模块直接读取
dumps.wikimedia.org 的目录索引，把“用哪一份转储”变成我们自己的决定。
"""

from __future__ import annotations

import re
from typing import Optional

import requests

import net

DUMP_BASE = "https://dumps.wikimedia.org"

# 目录索引里的转储日期形如 <a href="20260801/">
_DATE_RE = re.compile(r'href="(\d{8})/"')


def titles_filename(wiki: str, date: str) -> str:
    return f"{wiki}-{date}-all-titles-in-ns0.gz"


def titles_url(wiki: str, date: str) -> str:
    return f"{DUMP_BASE}/{wiki}/{date}/{titles_filename(wiki, date)}"


def list_dump_dates(wiki: str, session: Optional[requests.Session] = None) -> list[str]:
    """列出某个站点全部转储日期，按时间倒序。"""
    s = session or net.new_session()
    resp = s.get(f"{DUMP_BASE}/{wiki}/", timeout=net.TIMEOUT)
    resp.raise_for_status()
    dates = sorted(set(_DATE_RE.findall(resp.text)), reverse=True)
    return dates


def has_titles_dump(
    wiki: str, date: str, session: Optional[requests.Session] = None
) -> bool:
    """
    校验该日期的标题转储是否已生成。

    目录先于文件出现：转储任务运行中时目录已存在但 all-titles 尚未产出，
    因此必须逐个 HEAD 探测，不能只看目录列表。
    """
    s = session or net.new_session()
    resp = s.head(titles_url(wiki, date), timeout=net.TIMEOUT, allow_redirects=True)
    return resp.status_code == 200


def latest_dump_date(
    wiki: str,
    session: Optional[requests.Session] = None,
    max_probe: int = 6,
) -> str:
    """
    返回最新一份**已生成标题转储**的日期（YYYYMMDD）。

    Args:
        max_probe: 最多向前回溯探测多少个转储日期，避免站点异常时无限翻找。

    Raises:
        RuntimeError: 探测范围内没有可用转储。
    """
    dates = list_dump_dates(wiki, session)
    for date in dates[:max_probe]:
        if has_titles_dump(wiki, date, session):
            return date
    raise RuntimeError(
        f"{wiki}: 最近 {max_probe} 个转储目录中均未找到 all-titles-in-ns0 文件"
    )


if __name__ == "__main__":
    for _wiki in ("zhwiki", "zhwiktionary", "zhwikisource"):
        print(f"{_wiki}: {latest_dump_date(_wiki)}")
