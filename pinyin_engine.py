from __future__ import annotations

import importlib
import threading
from typing import Iterator

import requests

_pypinyin = importlib.import_module("pypinyin")
Style = _pypinyin.Style
pinyin = _pypinyin.pinyin
load_phrases_dict = _pypinyin.load_phrases_dict
load_single_dict = _pypinyin.load_single_dict

SINGLE_DICT_URL = "https://raw.githubusercontent.com/amzxyz/RIME-LMDG/wanxiang/pinyin_data/单字.dict.yaml"
PHRASE_DICT_URL = "https://raw.githubusercontent.com/amzxyz/RIME-LMDG/wanxiang/pinyin_data/词组.dict.yaml"
REQUEST_TIMEOUT_SECONDS = 10

_CUSTOM_DATA_LOCK = threading.Lock()
_CUSTOM_DATA_LOADED = False
_CUSTOM_DATA_ATTEMPTED = False


def _is_chinese_char(char: str) -> bool:
    code = ord(char)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x2EBEF
    )


def _download_text(url: str) -> str:
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.text


def _iter_rime_entries(content: str) -> Iterator[tuple[str, str]]:
    saw_yaml_start = False
    in_data_body = False

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line == "---":
            saw_yaml_start = True
            in_data_body = False
            continue
        if line == "...":
            in_data_body = True
            continue

        if saw_yaml_start and not in_data_body:
            continue

        columns = raw_line.split("\t")
        if len(columns) < 2:
            continue

        word = columns[0].strip()
        toned_pinyin = columns[1].strip()
        if word and toned_pinyin:
            yield word, toned_pinyin


def _parse_single_dict(content: str) -> dict[int, str]:
    single_map: dict[int, str] = {}
    for word, toned_pinyin in _iter_rime_entries(content):
        if len(word) != 1:
            continue
        syllables = toned_pinyin.split()
        if not syllables:
            continue
        single_map[ord(word)] = ",".join(syllables)
    return single_map


def _parse_phrase_dict(content: str) -> dict[str, list[list[str]]]:
    phrase_map: dict[str, list[list[str]]] = {}
    for word, toned_pinyin in _iter_rime_entries(content):
        if len(word) <= 1:
            continue
        syllables = toned_pinyin.split()
        if len(syllables) != len(word):
            continue
        phrase_map[word] = [[syllable] for syllable in syllables]
    return phrase_map


def load_custom_pinyin_data() -> bool:
    """下载并加载 RIME-LMDG 自定义拼音修正，成功返回 True。"""
    global _CUSTOM_DATA_LOADED
    global _CUSTOM_DATA_ATTEMPTED

    with _CUSTOM_DATA_LOCK:
        if _CUSTOM_DATA_LOADED:
            return True

        _CUSTOM_DATA_ATTEMPTED = True

        single_content = _download_text(SINGLE_DICT_URL)
        phrase_content = _download_text(PHRASE_DICT_URL)

        single_map = _parse_single_dict(single_content)
        phrase_map = _parse_phrase_dict(phrase_content)

        if phrase_map:
            load_phrases_dict(phrase_map)
        if single_map:
            load_single_dict(single_map)

        _CUSTOM_DATA_LOADED = True
        return True


def _ensure_custom_pinyin_data() -> None:
    global _CUSTOM_DATA_ATTEMPTED

    if _CUSTOM_DATA_LOADED or _CUSTOM_DATA_ATTEMPTED:
        return

    try:
        load_custom_pinyin_data()
    except requests.RequestException:
        _CUSTOM_DATA_ATTEMPTED = True
    except Exception:
        _CUSTOM_DATA_ATTEMPTED = True


def _normalize_syllables(word: str) -> list[str]:
    raw = pinyin(word, style=Style.TONE, heteronym=False, errors="default")
    syllables = [candidates[0] if candidates else "" for candidates in raw]
    if len(syllables) == len(word):
        return syllables

    fallback: list[str] = []
    for char in word:
        char_py = pinyin(char, style=Style.TONE, heteronym=False, errors="default")
        if char_py and char_py[0]:
            fallback.append(char_py[0][0])
        else:
            fallback.append(char)
    return fallback


def get_toned_pinyin(word: str) -> list[str]:
    """返回词语的逐字带声调拼音列表。"""
    if not word:
        return []
    _ensure_custom_pinyin_data()
    return _normalize_syllables(word)


def build_pro_pinyin(word: str, aux_map: dict[str, str]) -> str:
    """构建 pro 拼音格式：`拼音;辅助码`，词内空格分隔。"""
    if not word:
        return ""

    toned_syllables = get_toned_pinyin(word)
    result_parts: list[str] = []

    for index, char in enumerate(word):
        syllable = toned_syllables[index] if index < len(toned_syllables) else char
        aux_code = aux_map.get(char) if _is_chinese_char(char) else None
        if aux_code:
            result_parts.append(f"{syllable};{aux_code}")
        else:
            result_parts.append(syllable)

    return " ".join(result_parts)


if __name__ == "__main__":
    sample_word = "不能同意更多"
    sample_aux = {
        "不": "kx",
        "能": "bq",
        "同": "u",
        "意": "pw",
        "更": "a",
        "多": "e",
    }

    print(get_toned_pinyin("不能"))
    print(build_pro_pinyin(sample_word, sample_aux))
