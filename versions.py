"""
构建记录：追踪每个词典变体最近一次成功构建所依据的上游数据版本。

与旧版“上游 Release 版本号”不同，这里记录的是**原始数据源**的版本标识，
因为本项目自行从原始数据构建词典，不再等待上游发布产物：

- zhwiki / zhwiktionary / zhwikisource：Wikimedia 转储日期（YYYYMMDD）
- web-slang：上游维基页面 wikitext 的 sha256 前 16 位
- moegirl：标题来源标识（``api:<抓取日期>`` 或 ``upstream:<上游 tag>``）

记录格式（versions.json）::

    {
      "zhwiki": {"id": "20260801", "built": "2026-08-24"},
      ...
    }

``id`` 用于判断“上游数据是否变化”，``built`` 用于按周期触发无法廉价探测变化的
数据源（目前只有 moegirl）。
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Optional

VERSIONS_PATH = "versions.json"

# 全部词典变体；顺序即默认构建顺序（便宜的排前面）
VARIANTS = (
    "web-slang",
    "zhwiktionary",
    "zhwikisource",
    "zhwiki",
    "moegirl",
)


def load(path: str = VERSIONS_PATH) -> dict[str, dict[str, str]]:
    """
    读取构建记录。文件缺失、损坏或字段类型异常时返回空记录，
    使调用方退化为“全量构建”，而不是中断流程。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠️  构建记录不可用（{path}）：{e}；按全量构建处理")
        return {}

    if not isinstance(data, dict):
        return {}

    records: dict[str, dict[str, str]] = {}
    for variant, record in data.items():
        if isinstance(record, dict):
            records[variant] = {
                "id": str(record.get("id", "")),
                "built": str(record.get("built", "")),
            }
    return records


def save(records: dict[str, dict[str, str]], path: str = VERSIONS_PATH) -> None:
    """写回构建记录，按变体名排序以保证 diff 稳定。"""
    ordered = {k: records[k] for k in sorted(records)}
    Path(path).write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def make_record(source_id: str, built: Optional[_dt.date] = None) -> dict[str, str]:
    """构造一条构建记录。"""
    day = built or _dt.date.today()
    return {"id": source_id, "built": day.isoformat()}


def age_days(record: Optional[dict[str, str]], today: Optional[_dt.date] = None) -> int:
    """
    距离上次成功构建的天数。无记录或日期不可解析时返回一个足够大的值，
    让调用方按“必须重建”处理。
    """
    if not record:
        return 10**6
    try:
        built = _dt.date.fromisoformat(record.get("built", ""))
    except ValueError:
        return 10**6
    return ((today or _dt.date.today()) - built).days
