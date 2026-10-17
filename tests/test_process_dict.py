"""process_dict 词条取舍与编码的回归测试（运行：python -m unittest discover tests）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pinyin_engine  # noqa: E402
from process_dict import _process_data_line  # noqa: E402


class ProcessDataLineTest(unittest.TestCase):
    def setUp(self) -> None:
        # 跳过 RIME-LMDG 拼音修正数据的联网下载，保证测试确定、离线可跑
        patcher = mock.patch.object(pinyin_engine, "_CUSTOM_DATA_ATTEMPTED", True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _syllables(self, line: str) -> list[str]:
        out = _process_data_line(line, 1, {})
        self.assertIsNotNone(out, f"纯汉字词条被误删：{line!r}")
        assert out is not None
        return out.rstrip("\n").split("\t")[1].split(" ")

    def test_keeps_extension_g_and_h_hanzi(self) -> None:
        # U+31CEA（扩展 H）与 U+30EDD（扩展 G）均为汉字，pypinyin 有读音
        self.assertEqual(self._syllables("下\U00031cea镇\txia dai zhen\n"), ["xià", "dài", "zhèn"])
        self.assertEqual(
            self._syllables("\U00030edd\U00030edd儿面\tbiang biang er mian\n"),
            ["biáng", "biáng", "ér", "miàn"],
        )

    def test_separators_stay_in_word_but_not_in_code(self) -> None:
        out = _process_data_line("乔治·华盛顿\tqiao zhi hua sheng dun\n", 1, {})
        self.assertEqual(out, "乔治·华盛顿\tqiáo zhì huá shèng dùn\n")

    def test_drops_entries_with_letters_or_without_hanzi(self) -> None:
        for line in ("A-A战线\tA A zhan xian\n", "E的π次方\tE de pi ci fang\n", "-desh\tD E S H\n", "——\t\n"):
            with self.subTest(line=line):
                self.assertIsNone(_process_data_line(line, 1, {}))


if __name__ == "__main__":
    unittest.main()
