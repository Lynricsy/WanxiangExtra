#!/usr/bin/env python3
"""
词典自建流水线：直接从**原始数据源**构建 RIME 词典，不等待上游发布产物。

数据链路：

| 变体                                   | 原始数据                                   | 构建方式                                   |
|----------------------------------------|--------------------------------------------|--------------------------------------------|
| zhwiki / zhwiktionary / zhwikisource   | dumps.wikimedia.org 的 all-titles 转储     | 上游 fcitx5-pinyin-zhwiki 的 Makefile      |
| web-slang                              | zh.wikipedia.org 的《中国大陆网络用语列表》| 上游 zhwiki-web-slang.py + Makefile        |
| moegirl                                | zh.moegirl.org.cn MediaWiki API 标题       | 上游 mw2fcitx + pkg-moegirl 分支配置数据   |

上游**代码**每次构建时浅克隆最新版本，上游**发布节奏**不再影响我们：
Wikimedia 每出一份新转储、网络用语页面每改一次，我们都能立刻重建。

产物为未加工的 ``<变体>.dict.yaml``，随后交给 process_dict.py 生成 ``.pro.dict.yaml``。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import requests

import dump_index
import net
import upstream
import versions

# 变体 → Wikimedia 站点名
WIKI_SITES = {
    "zhwiki": "zhwiki",
    "zhwiktionary": "zhwiktionary",
    "zhwikisource": "zhwikisource",
}

MOEGIRL_TITLES_RELEASE = "https://api.github.com/repos/outloudvi/mw2fcitx/releases/latest"


# --------------------------------------------------------------------------
# 通用工具
# --------------------------------------------------------------------------


def _publish(src: Path, raw_dir: Path, variant: str) -> Path:
    """把构建产物收敛到统一的原始词典目录。"""
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / f"{variant}.dict.yaml"
    shutil.copyfile(src, dest)
    print(f"✅  {variant}: {dest} ({dest.stat().st_size / 1024:.0f} KiB)")
    return dest


def _drop_stale(repo: Path, variant: str) -> None:
    """强制重建时清掉 make 的中间产物，否则 make 会判定目标已是最新。"""
    for name in (
        f"{variant}.dict.yaml",
        f"{variant}.rime.raw",
        f"{variant}.raw",
        f"{variant}.raw.tmp",
        f"{variant}.source",
    ):
        (repo / name).unlink(missing_ok=True)


# --------------------------------------------------------------------------
# zhwiki / zhwiktionary / zhwikisource
# --------------------------------------------------------------------------


def build_wiki_variant(
    variant: str,
    repo: Path,
    raw_dir: Path,
    dump_date: str,
    force: bool,
) -> Path:
    """
    用上游 Makefile 构建维基系列词典。

    上游 Makefile 里的 ``VERSION`` 是硬编码的转储日期，这里用命令行变量覆盖，
    从而把“用哪份转储”的决定权拿到我们手上（make 命令行变量优先级最高）。
    """
    if force:
        _drop_stale(repo, variant)
    upstream.run(
        ["make", f"{variant}.dict.yaml", f"VERSION={dump_date}"],
        cwd=repo,
        env=upstream.script_env(),
    )
    return _publish(repo / f"{variant}.dict.yaml", raw_dir, variant)


# --------------------------------------------------------------------------
# web-slang
# --------------------------------------------------------------------------


def fetch_web_slang_wikitext(repo: Path) -> str:
    """抓取《中国大陆网络用语列表》原始 wikitext（复用上游抓取脚本）。"""
    result = upstream.run(
        [sys.executable, "zhwiki-web-slang.py", "--fetch"],
        cwd=repo,
        env=upstream.script_env(),
        capture=True,
    )
    return result.stdout


def build_web_slang(
    repo: Path,
    raw_dir: Path,
    wikitext: str,
    stamp: str,
    force: bool,
) -> Path:
    """
    用已抓取的 wikitext 构建网络用语词典。

    先把 wikitext 写成 Makefile 期望的文件名，make 便不会重复抓取——
    页面内容已经在计算指纹时取过一次，没必要再打扰维基百科。
    """
    if force:
        _drop_stale(repo, "web-slang")
    (repo / f"web-slang-{stamp}.wikitext").write_text(wikitext, encoding="utf-8")
    upstream.run(
        ["make", "web-slang.dict.yaml", f"WEB_SLANG_VERSION={stamp}"],
        cwd=repo,
        env=upstream.script_env(),
    )
    return _publish(repo / "web-slang.dict.yaml", raw_dir, "web-slang")


# --------------------------------------------------------------------------
# moegirl
# --------------------------------------------------------------------------


def latest_upstream_titles(session: requests.Session) -> tuple[str, str]:
    """
    读取 mw2fcitx 最新 Release 中的 titles.txt（萌百 API 不可用时的备用标题源）。

    Returns:
        (release tag, 下载地址)

    Raises:
        RuntimeError: Release 中没有 titles.txt。
    """
    resp = session.get(MOEGIRL_TITLES_RELEASE, timeout=net.TIMEOUT)
    resp.raise_for_status()
    release = resp.json()
    for asset in release.get("assets", []):
        if asset.get("name") == "titles.txt":
            return release.get("tag_name", ""), asset["browser_download_url"]
    raise RuntimeError("mw2fcitx 最新 Release 中未找到 titles.txt")


def _mw2fcitx_bin(env: dict[str, str]) -> str:
    path = shutil.which("mw2fcitx", path=env.get("PATH"))
    if not path:
        raise RuntimeError("未找到 mw2fcitx 可执行文件，请先 pip install -r requirements.txt")
    return path


def build_moegirl(
    profile: Path,
    work: Path,
    raw_dir: Path,
    session: requests.Session,
    *,
    allow_fallback: bool = True,
    title_limit: int = -1,
    request_delay: float = 2.0,
    use_api: bool = True,
) -> tuple[Path, str]:
    """
    构建萌娘百科词典。

    首选直接抓取萌百 MediaWiki API 的标题清单；该 API 对部分来源 IP 返回
    ``action-notallowed``，此时退回到 mw2fcitx Release 里的 titles.txt——
    词典仍由我们自己构建，只是标题清单来自上游最近一次抓取。

    Returns:
        (产物路径, 标题来源标识)
    """
    work.mkdir(parents=True, exist_ok=True)
    output = work / "moegirl.dict.yaml"
    config = Path(__file__).resolve().parent / "moegirl_config.py"

    env = upstream.script_env()
    env.update(
        {
            "MOEGIRL_PROFILE_DIR": str(profile),
            "MOEGIRL_OUTPUT": str(output),
            "MOEGIRL_TITLES_OUTPUT": str(work / "titles.txt"),
            "MOEGIRL_REQUEST_DELAY": str(request_delay),
            "MOEGIRL_VERSION": _dt.date.today().strftime("%Y.%m.%d"),
        }
    )
    if title_limit > 0:
        env["MOEGIRL_TITLE_LIMIT"] = str(title_limit)

    binary = _mw2fcitx_bin(env)

    if use_api:
        try:
            upstream.run([binary, "-c", str(config)], cwd=work, env=env)
            return _publish(output, raw_dir, "moegirl"), f"api:{_dt.date.today():%Y%m%d}"
        except subprocess.CalledProcessError as e:
            if not allow_fallback:
                raise
            print(f"⚠️  萌百 API 抓取失败（退出码 {e.returncode}），回退到上游 titles.txt")

    tag, url = latest_upstream_titles(session)
    titles = work / "upstream-titles.txt"
    net.download(url, titles, session)
    env["MOEGIRL_API_PATH"] = ""
    env["MOEGIRL_TITLE_FILES"] = str(titles)
    upstream.run([binary, "-c", str(config)], cwd=work, env=env)
    return _publish(output, raw_dir, "moegirl"), f"upstream:{tag}"


# --------------------------------------------------------------------------
# 编排
# --------------------------------------------------------------------------


def _moegirl_needs_build(
    record: Optional[dict[str, str]],
    session: requests.Session,
    interval_days: int,
) -> tuple[bool, str]:
    """萌百没有廉价的“内容是否变化”信号，因此按构建周期 + 备用源版本判断。"""
    if not record or not record.get("id"):
        return True, "尚无构建记录"

    age = versions.age_days(record)
    if age >= interval_days:
        return True, f"距上次构建已 {age} 天（阈值 {interval_days} 天）"

    if record["id"].startswith("upstream:"):
        try:
            tag, _ = latest_upstream_titles(session)
        except Exception as e:  # 网络/接口异常不应阻断其他变体
            print(f"⚠️  无法检查上游标题清单版本：{e!r}")
            return False, "上游标题清单版本未知"
        if f"upstream:{tag}" != record["id"]:
            return True, f"上游标题清单更新至 {tag}"

    return False, f"{age} 天前构建于 {record['id']}"


def build(args: argparse.Namespace) -> int:
    session = net.new_session()
    records = versions.load(args.versions)
    raw_dir = Path(args.raw_dir).resolve()
    work = Path(args.work_dir).resolve()
    wanted = args.variant or list(versions.VARIANTS)

    failures: list[str] = []
    built: list[str] = []
    zhwiki_repo: Optional[Path] = None

    def ensure_zhwiki_repo() -> Path:
        nonlocal zhwiki_repo
        if zhwiki_repo is None:
            zhwiki_repo = upstream.sync_repo(
                upstream.ZHWIKI_REPO, upstream.ZHWIKI_BRANCH, work / "fcitx5-pinyin-zhwiki"
            )
            print(f"📦  fcitx5-pinyin-zhwiki @ {upstream.head_commit(zhwiki_repo)}")
        return zhwiki_repo

    for variant in wanted:
        record = records.get(variant)
        try:
            if variant in WIKI_SITES:
                dump_date = dump_index.latest_dump_date(WIKI_SITES[variant], session)
                if not args.force and record and record.get("id") == dump_date:
                    print(f"⏭️  {variant}: 转储 {dump_date} 已构建，跳过")
                    continue
                print(f"🔄  {variant}: 使用转储 {dump_date}（已记录 {record and record.get('id') or '无'}）")
                if args.dry_run:
                    continue
                build_wiki_variant(variant, ensure_zhwiki_repo(), raw_dir, dump_date, args.force)
                records[variant] = versions.make_record(dump_date)

            elif variant == "web-slang":
                repo = ensure_zhwiki_repo()
                wikitext = fetch_web_slang_wikitext(repo)
                digest = hashlib.sha256(wikitext.encode("utf-8")).hexdigest()[:16]
                if not args.force and record and record.get("id") == digest:
                    print(f"⏭️  web-slang: 页面内容未变（{digest}），跳过")
                    continue
                print(f"🔄  web-slang: 页面指纹 {digest}（已记录 {record and record.get('id') or '无'}）")
                if args.dry_run:
                    continue
                stamp = _dt.date.today().strftime("%Y%m%d")
                build_web_slang(repo, raw_dir, wikitext, stamp, args.force)
                records[variant] = versions.make_record(digest)

            elif variant == "moegirl":
                needed, reason = (True, "强制构建") if args.force else _moegirl_needs_build(
                    record, session, args.moegirl_interval_days
                )
                if not needed:
                    print(f"⏭️  moegirl: {reason}，跳过")
                    continue
                print(f"🔄  moegirl: {reason}")
                if args.dry_run:
                    continue
                profile = upstream.sync_repo(
                    upstream.MOEGIRL_REPO, upstream.MOEGIRL_BRANCH, work / "mw2fcitx-profile"
                )
                print(f"📦  mw2fcitx@pkg-moegirl @ {upstream.head_commit(profile)}")
                _, source_id = build_moegirl(
                    profile,
                    work / "moegirl",
                    raw_dir,
                    session,
                    allow_fallback=not args.no_moegirl_fallback,
                    title_limit=args.moegirl_title_limit,
                    request_delay=args.moegirl_request_delay,
                    use_api=not args.moegirl_offline,
                )
                records[variant] = versions.make_record(source_id)

            else:
                raise ValueError(f"未知变体：{variant}")

            built.append(variant)

        except Exception as e:  # 单个变体失败不应带走其他变体
            failures.append(variant)
            print(f"❌  {variant} 构建失败：{e!r}", file=sys.stderr)

    if built and not args.dry_run:
        versions.save(records, args.versions)

    print()
    print(f"构建完成：{', '.join(built) if built else '无（全部跳过）'}")
    if failures:
        print(f"构建失败：{', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_dicts.py",
        description="从原始数据源自建 RIME 词库（不依赖上游发布产物）",
    )
    parser.add_argument(
        "--variant",
        action="append",
        choices=list(versions.VARIANTS),
        help="只构建指定变体，可重复；默认构建全部",
    )
    parser.add_argument("--raw-dir", default="raw", help="原始词典输出目录")
    parser.add_argument("--work-dir", default="tmp/build", help="上游代码与中间产物目录")
    parser.add_argument("--versions", default=versions.VERSIONS_PATH, help="构建记录文件")
    parser.add_argument("--force", action="store_true", help="忽略构建记录，强制重建")
    parser.add_argument("--dry-run", action="store_true", help="只探测上游数据版本，不构建")
    parser.add_argument(
        "--moegirl-interval-days",
        type=int,
        default=int(os.environ.get("MOEGIRL_INTERVAL_DAYS", "30")),
        help="萌百重建周期（天），避免频繁全站抓取",
    )
    parser.add_argument(
        "--moegirl-request-delay",
        type=float,
        default=2.0,
        help="萌百 API 翻页间隔秒数",
    )
    parser.add_argument(
        "--moegirl-title-limit",
        type=int,
        default=-1,
        help="萌百标题数量上限，仅用于冒烟测试",
    )
    parser.add_argument(
        "--moegirl-offline",
        action="store_true",
        help="跳过萌百 API，直接使用上游 titles.txt",
    )
    parser.add_argument(
        "--no-moegirl-fallback",
        action="store_true",
        help="萌百 API 失败时直接报错，不回退到上游 titles.txt",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    return build(_build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
