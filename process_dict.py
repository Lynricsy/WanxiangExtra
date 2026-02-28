#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from pathlib import Path
from typing import Optional

from aux_loader import get_aux_map
from pinyin_engine import build_pro_pinyin


_YAML_HEADS = ("---", "name:", "version:", "sort:", "...")


def _contains_cjk(text: str) -> bool:
    for ch in text:
        code = ord(ch)
        if (
            0x3400 <= code <= 0x4DBF
            or 0x4E00 <= code <= 0x9FFF
            or 0xF900 <= code <= 0xFAFF
            or 0x20000 <= code <= 0x2EBEF
            or 0x2F800 <= code <= 0x2FA1F
        ):
            return True
    return False


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


def _process_data_line(line: str, line_no: int, aux_map: dict[str, str]) -> str:
    try:
        if not line.strip():
            return line
        if line.lstrip().startswith("#"):
            return line

        content, nl = _split_newline(line)
        if "\t" in content:
            cols = content.split("\t")
            if not cols:
                return line

            word_raw = cols[0]
            word = word_raw.strip()
            if not word or not _contains_cjk(word):
                return line

            enhanced = build_pro_pinyin(word, aux_map)
            out_cols = [word, enhanced]
            if len(cols) > 2:
                out_cols.extend(cols[2:])
            return "\t".join(out_cols) + nl

        word = content.strip()
        if not word or not _contains_cjk(word):
            return line
        enhanced = build_pro_pinyin(word, aux_map)
        return f"{word}\t{enhanced}{nl}"
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
        for idx, raw in enumerate(f_in):
            line_no = idx + 1
            if idx < len(_YAML_HEADS):
                if raw.lstrip().startswith(("name:", "version:")):
                    f_out.write(_rewrite_header_line(raw, today))
                else:
                    f_out.write(raw)
                continue

            f_out.write(_process_data_line(raw, line_no, aux_map))


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
