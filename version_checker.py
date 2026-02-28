"""
version_checker.py

检查上游 RIME 词库仓库的 GitHub Releases，与本地存储的版本进行比较，
并提供新版本的下载 URL。

支持的上游仓库：
- outloudvi/mw2fcitx: 萌百词库，tag 为日期格式（如 20260209）
- felixonmars/fcitx5-pinyin-zhwiki: 维基百科拼音词库，tag 为 semver（如 0.3.0）
"""

import json
import os
import re
from typing import Optional

import requests

# 默认版本文件路径
VERSIONS_PATH = "versions.json"

# 需要追踪的上游仓库配置
REPOS = {
    "mw2fcitx": {
        "owner": "outloudvi",
        "repo": "mw2fcitx",
    },
    "fcitx5-pinyin-zhwiki": {
        "owner": "felixonmars",
        "repo": "fcitx5-pinyin-zhwiki",
    },
}

# fcitx5-pinyin-zhwiki 中的词库变体名称前缀
ZHWIKI_VARIANTS = ["zhwiki", "zhwiktionary", "zhwikisource", "web-slang"]


def _get_github_headers() -> dict:
    """构建 GitHub API 请求头，可选支持 GITHUB_TOKEN 鉴权。"""
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def get_latest_release(owner: str, repo: str) -> dict:
    """
    通过 GitHub API 获取指定仓库的最新 Release 信息。

    Args:
        owner: 仓库所有者（如 "outloudvi"）
        repo: 仓库名称（如 "mw2fcitx"）

    Returns:
        包含 tag_name 和 assets 列表的字典。
        格式：{"tag_name": "20260209", "assets": [{"name": "...", "browser_download_url": "..."}]}
        若出错则返回空字典。
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    headers = _get_github_headers()

    try:
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code == 403:
            # API 速率限制
            rate_limit_reset = response.headers.get("X-RateLimit-Reset", "未知")
            print(f"⚠️  GitHub API 速率限制，重置时间戳: {rate_limit_reset}")
            print("   建议设置 GITHUB_TOKEN 环境变量以提高速率限制。")
            return {}

        if response.status_code == 404:
            print(f"⚠️  仓库未找到: {owner}/{repo}")
            return {}

        response.raise_for_status()
        data = response.json()

        return {
            "tag_name": data.get("tag_name", ""),
            "assets": data.get("assets", []),
        }

    except requests.exceptions.Timeout:
        print(f"⚠️  请求超时: {owner}/{repo}")
        return {}
    except requests.exceptions.ConnectionError:
        print(f"⚠️  网络连接错误: {owner}/{repo}")
        return {}
    except requests.exceptions.HTTPError as e:
        print(f"⚠️  HTTP 错误 ({owner}/{repo}): {e}")
        return {}
    except (KeyError, ValueError) as e:
        print(f"⚠️  解析 Release 数据失败 ({owner}/{repo}): {e}")
        return {}


def load_versions(path: str = VERSIONS_PATH) -> dict:
    """
    从 JSON 文件读取本地存储的版本信息。

    Args:
        path: versions.json 文件路径

    Returns:
        版本信息字典，若文件不存在则返回默认结构。
        格式：{"mw2fcitx": "", "fcitx5-pinyin-zhwiki": ""}
    """
    if not os.path.exists(path):
        return {
            "mw2fcitx": "",
            "fcitx5-pinyin-zhwiki": "",
        }

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️  读取版本文件失败 ({path}): {e}")
        return {
            "mw2fcitx": "",
            "fcitx5-pinyin-zhwiki": "",
        }


def save_versions(versions: dict, path: str = VERSIONS_PATH) -> None:
    """
    将版本信息写入 JSON 文件。

    Args:
        versions: 版本信息字典
        path: 目标 versions.json 文件路径
    """
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(versions, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"⚠️  写入版本文件失败 ({path}): {e}")


def _extract_mw2fcitx_assets(assets: list) -> dict:
    """
    从 mw2fcitx release 的 assets 中提取萌百词库下载 URL。

    Args:
        assets: GitHub API 返回的 assets 列表

    Returns:
        {"moegirl": "下载URL"} 格式的字典
    """
    result = {}
    for asset in assets:
        name = asset.get("name", "")
        url = asset.get("browser_download_url", "")
        if name == "moegirl.dict.yaml" and url:
            result["moegirl"] = url
            break
    return result


def _extract_zhwiki_assets(assets: list) -> dict:
    """
    从 fcitx5-pinyin-zhwiki release 的 assets 中提取各词库变体的下载 URL。
    当一个变体存在多个日期版本时，选取日期最新的那个。

    Args:
        assets: GitHub API 返回的 assets 列表

    Returns:
        {"zhwiki": "url", "zhwiktionary": "url", ...} 格式的字典
    """
    # 按变体名称分组，记录 (日期字符串, URL)
    variant_candidates: dict[str, list[tuple[str, str]]] = {
        v: [] for v in ZHWIKI_VARIANTS
    }

    for asset in assets:
        name = asset.get("name", "")
        url = asset.get("browser_download_url", "")
        if not url:
            continue

        # 匹配格式：{variant}-YYYYMMDD.dict.yaml
        for variant in ZHWIKI_VARIANTS:
            # web-slang 连字符需要转义
            pattern = rf"^{re.escape(variant)}-(\d{{8}})\.dict\.yaml$"
            m = re.match(pattern, name)
            if m:
                date_str = m.group(1)
                variant_candidates[variant].append((date_str, url))
                break

    result = {}
    for variant, candidates in variant_candidates.items():
        if candidates:
            # 选取日期最新的（字符串比较即可，格式为 YYYYMMDD）
            candidates.sort(key=lambda x: x[0], reverse=True)
            result[variant] = candidates[0][1]

    return result


def check_updates(versions_path: str = VERSIONS_PATH) -> dict:
    """
    检查所有上游仓库是否有新版本可用。

    流程：
    1. 加载本地 versions.json 中存储的版本号
    2. 从 GitHub API 获取每个仓库的最新 release
    3. 比对 tag_name，若不同则加入结果
    4. 返回需要更新的仓库及其下载信息

    Args:
        versions_path: versions.json 文件路径

    Returns:
        需要更新的仓库字典。若无需更新则返回空字典。
        格式示例：
        {
            "mw2fcitx": {
                "tag": "20260209",
                "assets": {"moegirl": "https://..."}
            },
            "fcitx5-pinyin-zhwiki": {
                "tag": "0.3.0",
                "assets": {
                    "zhwiki": "https://...",
                    "zhwiktionary": "https://...",
                    "zhwikisource": "https://...",
                    "web-slang": "https://..."
                }
            }
        }
    """
    local_versions = load_versions(versions_path)
    updates = {}

    for key, config in REPOS.items():
        owner = config["owner"]
        repo = config["repo"]
        local_tag = local_versions.get(key, "")

        release = get_latest_release(owner, repo)
        if not release:
            print(f"⚠️  跳过 {key}（无法获取 Release 信息）")
            continue

        latest_tag = release.get("tag_name", "")
        assets_list = release.get("assets", [])

        if not latest_tag:
            print(f"⚠️  {key} 返回的 tag_name 为空，跳过")
            continue

        # 空字符串（从未检查过）也视为需要更新
        if local_tag == latest_tag:
            print(f"✅  {key} 已是最新版本: {latest_tag}")
            continue

        print(f"🔄  {key} 发现新版本: {local_tag!r} → {latest_tag!r}")

        # 提取各仓库对应的 assets
        if key == "mw2fcitx":
            asset_urls = _extract_mw2fcitx_assets(assets_list)
        elif key == "fcitx5-pinyin-zhwiki":
            asset_urls = _extract_zhwiki_assets(assets_list)
        else:
            asset_urls = {}

        updates[key] = {
            "tag": latest_tag,
            "assets": asset_urls,
        }

    return updates


def download_file(url: str, dest: str) -> None:
    """
    使用流式下载将远程文件保存到本地，避免大文件 OOM。

    Args:
        url: 文件下载地址
        dest: 本地保存路径（含文件名）
    """
    headers = _get_github_headers()
    chunk_size = 8192  # 8KB

    try:
        with requests.get(url, headers=headers, stream=True, timeout=60) as response:
            response.raise_for_status()
            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0

            with open(dest, "wb") as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = downloaded / total_size * 100
                            print(
                                f"\r  下载中... {downloaded / 1024 / 1024:.1f}MB"
                                f" / {total_size / 1024 / 1024:.1f}MB"
                                f" ({percent:.1f}%)",
                                end="",
                                flush=True,
                            )

        if total_size > 0:
            print()  # 换行
        print(f"✅  下载完成: {dest}")

    except requests.exceptions.Timeout:
        print(f"\n⚠️  下载超时: {url}")
        raise
    except requests.exceptions.HTTPError as e:
        print(f"\n⚠️  下载 HTTP 错误: {e}")
        raise
    except OSError as e:
        print(f"\n⚠️  文件写入失败 ({dest}): {e}")
        raise


if __name__ == "__main__":
    print("=" * 60)
    print("RIME 词库版本检查工具")
    print("=" * 60)

    # 显示当前本地版本
    current_versions = load_versions(VERSIONS_PATH)
    print("\n📋 当前本地版本：")
    for name, tag in current_versions.items():
        tag_display = tag if tag else "（从未检查）"
        print(f"  • {name}: {tag_display}")

    # 检查上游更新
    print("\n🔍 正在检查上游更新...\n")
    updates = check_updates(VERSIONS_PATH)

    if not updates:
        print("\n🎉 所有词库均已是最新版本！")
    else:
        print(f"\n📦 发现 {len(updates)} 个仓库需要更新：")
        for name, info in updates.items():
            print(f"\n  [{name}]")
            print(f"    新版本 Tag: {info['tag']}")
            print(f"    可下载资源：")
            for variant, url in info["assets"].items():
                print(f"      • {variant}: {url}")
