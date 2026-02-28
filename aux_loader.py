#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aux_loader.py — 下载并解析 RIME-LMDG 辅助码数据，提取墨奇（Moqi）辅助码映射。

文件格式说明：
    尽管后缀为 .yaml，实际上是制表符分隔的纯文本：
    每行格式：字符\t;zrm;flypy;moqi;hanxin;shouyou;tiger;wubi;unknown;
    示例：呵\t;kk;kk;kk;oj;rr;dz;ks;kk;
    墨奇码位于 split(';')[3]（0-indexed，第0位是空字符串因为行以 ; 开头）
"""

from __future__ import annotations

import logging
from typing import Optional

import requests

# 默认数据源 URL（RIME-LMDG wanxiang 分支辅助码文件）
DEFAULT_URL = "https://raw.githubusercontent.com/amzxyz/RIME-LMDG/wanxiang/scripts/auxiliary_code.yaml"

# 列索引：split(';') 后各辅助码方案位置
# [0]='' (行首分号前), [1]=zrm, [2]=flypy, [3]=moqi, [4]=hanxin, ...
_MOQI_INDEX = 3

logger = logging.getLogger(__name__)


def download_aux_code(url: str = DEFAULT_URL, timeout: int = 30) -> str:
    """从指定 URL 下载辅助码数据文件，返回原始文本内容。

    Args:
        url: 数据文件的 URL，默认为 RIME-LMDG 的 auxiliary_code.yaml。
        timeout: HTTP 请求超时时间（秒），默认 30。

    Returns:
        文件的原始文本内容（UTF-8 解码）。

    Raises:
        requests.RequestException: 网络请求失败时抛出。
    """
    logger.info("正在下载辅助码数据：%s", url)
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = "utf-8"
    logger.info("下载完成，共 %d 字节", len(response.content))
    return response.text


def load_moqi_map(text: str) -> dict[str, str]:
    """从辅助码数据文本中解析墨奇（Moqi）辅助码映射。

    文件格式为制表符分隔的纯文本（非 YAML dict），每行：
        字符\\t;zrm;flypy;moqi;hanxin;shouyou;tiger;wubi;unknown;

    Args:
        text: 辅助码数据文件的原始文本内容。

    Returns:
        字典 {汉字: 墨奇辅助码}，只包含有效的单个汉字条目。
        若某字的墨奇码为空则跳过该字。
    """
    moqi_map: dict[str, str] = {}
    skipped_empty = 0
    skipped_malformed = 0

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        # 跳过空行和注释行
        if not line or line.startswith("#"):
            continue

        # 按制表符分割：[字符, ;code1;code2;...]
        parts = line.split("\t")
        if len(parts) < 2:
            logger.debug("第 %d 行格式错误（无制表符）：%r", line_no, line[:40])
            skipped_malformed += 1
            continue

        char = parts[0]

        # 只处理单个汉字
        if len(char) != 1:
            skipped_malformed += 1
            continue

        # 解析辅助码列：split(';') => ['', zrm, flypy, moqi, ...]
        code_segment = parts[1]
        code_parts = code_segment.split(";")

        if len(code_parts) <= _MOQI_INDEX:
            logger.debug("第 %d 行辅助码列不足：%r", line_no, line[:40])
            skipped_malformed += 1
            continue

        moqi_code = code_parts[_MOQI_INDEX].strip()

        # 跳过墨奇码为空的条目
        if not moqi_code:
            skipped_empty += 1
            continue

        # 若有多个候选码（逗号分隔），取第一个
        if "," in moqi_code:
            moqi_code = moqi_code.split(",")[0].strip()

        moqi_map[char] = moqi_code

    logger.info(
        "墨奇辅助码解析完成：共 %d 条，跳过空码 %d 条，格式异常 %d 条",
        len(moqi_map),
        skipped_empty,
        skipped_malformed,
    )
    return moqi_map


def get_aux_map(url: str = DEFAULT_URL, timeout: int = 30) -> dict[str, str]:
    """便捷函数：下载并解析墨奇辅助码映射，一步到位。

    Args:
        url: 数据文件的 URL，默认为 RIME-LMDG 的 auxiliary_code.yaml。
        timeout: HTTP 请求超时时间（秒），默认 30。

    Returns:
        字典 {汉字: 墨奇辅助码}。

    Raises:
        requests.RequestException: 网络请求失败时抛出。
    """
    text = download_aux_code(url=url, timeout=timeout)
    return load_moqi_map(text)


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    print("正在获取墨奇辅助码映射...")
    try:
        aux_map = get_aux_map()
    except requests.RequestException as e:
        print(f"✗ 网络错误：{e}", file=sys.stderr)
        sys.exit(1)

    print(f"✓ 共加载 {len(aux_map)} 个汉字的墨奇辅助码")
    print("\n示例条目（前10个）：")
    for char, code in list(aux_map.items())[:10]:
        print(f"  {char!r} → {code!r}")
