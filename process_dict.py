#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from pathlib import Path
from typing import Optional

from aux_loader import get_aux_map
from pinyin_engine import build_pro_pinyin, is_hanzi


_YAML_HEADS = ("---", "name:", "version:", "sort:", "...")

# 上游 convert.py 注音前剔除的间隔号与连字符（_INTERPUNCT_TRANSTAB）；
# 词条本身保留它们，编码里不能出现——万象的拼写运算无法从键盘输入这些音节。
_SEPARATORS = str.maketrans("", "", "·-‐–—")


def _encodable_text(word: str) -> Optional[str]:
    """
    返回用于注音的纯汉字串。

    去掉间隔号后仍含汉字以外的字符（拉丁/希腊字母等）时返回 None：万象 pro
    词库只收纯汉字词条，字母混排词条归 mixedcode 词库，放进来也打不出。
    """
    text = word.translate(_SEPARATORS)
    if text and all(is_hanzi(ch) for ch in text):
        return text
    return None


def _split_newline(line: str) -> tuple[str, str]:
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


_HEADER_KV_RE = re.compile(
    r"^(?P<indent>\s*)(?P<key>name|version):\s*(?P<value>.*?)(?P<comment>\s*#.*)?$"
)


def _rewrite_header_line(line: str, today: str) -> str:
    content, nl = _split_newline(line)
    m = _HEADER_KV_RE.match(content)
    if not m:
        return line

    indent = m.group("indent")
    key = m.group("key")
    value = (m.group("value") or "").strip()
    comment = m.group("comment") or ""

    quote = ""
    if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
        quote = value[0]
        value_inner = value[1:-1]
    else:
        value_inner = value

    if key == "name":
        if value_inner and not value_inner.endswith(".pro"):
            value_inner = f"{value_inner}.pro"
        new_value = f"{quote}{value_inner}{quote}" if quote else value_inner
        return f"{indent}name: {new_value}{comment}{nl}"

    quote_char = quote or '"'
    new_value = f"{quote_char}{today}{quote_char}"
    return f"{indent}version: {new_value}{comment}{nl}"


def _process_data_line(line: str, line_no: int, aux_map: dict[str, str]) -> Optional[str]:
    """加工一行词条；返回 None 表示该词条应丢弃。"""
    try:
        if not line.strip():
            return line
        if line.lstrip().startswith("#"):
            return line

        content, nl = _split_newline(line)
        cols = content.split("\t")
        word = cols[0].strip()
        text = _encodable_text(word)
        if text is None:
            return None

        out_cols = [word, build_pro_pinyin(text, aux_map), *cols[2:]]
        return "\t".join(out_cols) + nl
    except Exception as e:
        print(f"[WARN] 第 {line_no} 行处理失败：{e!r}；已原样保留该行", file=sys.stderr)
        return line


def process_file(input_path: str, output_path: str, aux_map: dict[str, str]) -> None:
    in_path = Path(input_path)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    today = _dt.date.today().strftime("%Y.%m.%d")

    with (
        in_path.open("r", encoding="utf-8") as f_in,
        out_path.open("w", encoding="utf-8") as f_out,
    ):
        dropped = 0
        for idx, raw in enumerate(f_in):
            line_no = idx + 1
            if idx < len(_YAML_HEADS):
                if raw.lstrip().startswith(("name:", "version:")):
                    f_out.write(_rewrite_header_line(raw, today))
                else:
                    f_out.write(raw)
                continue

            processed = _process_data_line(raw, line_no, aux_map)
            if processed is None:
                dropped += 1
            else:
                f_out.write(processed)

    if dropped:
        print(f"[INFO] {in_path.name}：丢弃 {dropped} 条含非汉字字符的词条", file=sys.stderr)


def process_all(
    input_files: list[tuple[str, str]],
    output_dir: str,
    aux_map: dict[str, str],
) -> None:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for input_path, output_name in input_files:
        out_path = out_dir / output_name
        process_file(input_path, str(out_path), aux_map)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="process_dict.py",
        description="逐行流式处理 RIME dict.yaml：追加 .pro 名称、更新版本日期、生成带声调拼音与辅助码",
    )
    parser.add_argument("input", help="输入 dict.yaml 路径")
    parser.add_argument("output", help="输出 dict.yaml 路径")
    parser.add_argument(
        "--aux-url",
        default=None,
        help="辅助码映射数据 URL（默认使用 aux_loader.DEFAULT_URL）",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    try:
        aux_map = get_aux_map(url=args.aux_url) if args.aux_url else get_aux_map()
    except Exception as e:
        print(f"[ERROR] 获取辅助码映射失败：{e!r}", file=sys.stderr)
        return 2

    try:
        process_file(args.input, args.output, aux_map)
    except FileNotFoundError as e:
        print(f"[ERROR] 文件不存在：{e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"[ERROR] 文件读写失败：{e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
