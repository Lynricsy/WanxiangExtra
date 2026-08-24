"""
mw2fcitx 构建配置（萌娘百科）。

与上游 pkg-moegirl 分支的 utils/moegirl_dict.py 的差别只有一处：**去掉依赖
libime 的 pinyin 生成器**，只产出 RIME 词典——本项目只需要 dict.yaml，
不需要 fcitx5 二进制词典，也就不必在 CI 里拉 Arch 容器装 libime。

繁简/替换 tweaks 与拼音修正表仍直接复用上游 pkg-moegirl 分支的数据，
以便跟随上游对词条清洗规则的修正。

环境变量：
- MOEGIRL_PROFILE_DIR   pkg-moegirl 分支克隆目录（必填）
- MOEGIRL_OUTPUT        输出 dict.yaml 路径（默认 moegirl.dict.yaml）
- MOEGIRL_TITLES_OUTPUT 抓取到的标题清单落盘路径（默认 titles.txt）
- MOEGIRL_API_PATH      MediaWiki API 地址；置空则完全使用本地标题文件
- MOEGIRL_TITLE_FILES   额外标题文件，os.pathsep 分隔（回退到上游 titles.txt 时使用）
- MOEGIRL_TITLE_LIMIT   标题数量上限，仅用于冒烟测试
- MOEGIRL_REQUEST_DELAY API 翻页间隔秒数（默认 2，避免给上游站点压力）
- MOEGIRL_VERSION       写入词典头部的 version 字段
"""

from __future__ import annotations

import os
from pathlib import Path

from mw2fcitx.tweaks.moegirl import (
    tweak_opencc_t2s,
    tweak_replace_characters,
    tweaks,
)

_PROFILE_DIR = Path(os.environ["MOEGIRL_PROFILE_DIR"]).resolve()

_title_files = [str(_PROFILE_DIR / "extras" / "pcr.txt")]
_extra_files = os.environ.get("MOEGIRL_TITLE_FILES", "")
if _extra_files:
    _title_files.extend(p for p in _extra_files.split(os.pathsep) if p)

_kwargs: dict[str, object] = {
    "output": os.environ.get("MOEGIRL_TITLES_OUTPUT", "titles.txt"),
    "request_delay": float(os.environ.get("MOEGIRL_REQUEST_DELAY", "2")),
}

_limit = int(os.environ.get("MOEGIRL_TITLE_LIMIT", "-1"))
if _limit > 0:
    _kwargs["title_limit"] = _limit

_source: dict[str, object] = {
    "file_path": _title_files,
    "kwargs": _kwargs,
}

_api_path = os.environ.get("MOEGIRL_API_PATH", "https://mobile.moegirl.org.cn/api.php")
if _api_path:
    _source["api_path"] = _api_path

exports = {
    "source": _source,
    "tweaks": tweaks + [
        tweak_opencc_t2s,
        # 上游修正：「筿」在萌百语境下应按「篠」注音
        tweak_replace_characters({"筿": "篠"}),
    ],
    "converter": {
        "use": "pypinyin",
        "kwargs": {"fixfile": str(_PROFILE_DIR / "fixfile.json")},
    },
    "generator": [
        {
            "use": "rime",
            "kwargs": {
                "name": "moegirl",
                "version": os.environ.get("MOEGIRL_VERSION", "0.1"),
                "output": os.environ.get("MOEGIRL_OUTPUT", "moegirl.dict.yaml"),
            },
        }
    ],
}
