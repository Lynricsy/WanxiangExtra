# WanxiangExtra

自动化 RIME 词库流水线：**自行从原始数据构建**中文维基系列与萌娘百科词库，再为其添加带声调拼音与墨奇辅助码，生成可直接部署的 `.pro.dict.yaml` 词典文件。

## 功能特性

- **不等上游发版**：直接读取 Wikimedia 转储索引与维基站点数据自行构建，上游仓库是否发布产物、何时发布，都不再影响我们的更新节奏
- **跟随上游代码**：每次构建浅克隆上游构建脚本（Makefile / convert.py / mw2fcitx）的最新版本，词条清洗与注音规则的修正会自动生效
- **按数据变化触发**：转储日期、页面内容指纹分别作为各变体的版本标识，只重建真正发生变化的词典
- **带声调拼音标注**：使用 pypinyin 引擎为每个汉字生成准确的声调拼音，并集成 RIME-LMDG 自定义拼音修正数据
- **墨奇辅助码附加**：自动下载并解析 RIME-LMDG 辅助码数据，为每个汉字附加墨奇（Moqi）辅助码
- **流式逐行处理**：加工阶段逐行读写，避免大文件一次性加载导致的内存问题
- **滚动发布**：始终维护一个 `latest` Release，本次未重建的变体保留上一次的可下载产物

## 输出文件

| 文件名 | 原始数据源 | 说明 |
|--------|------------|------|
| `zhwiki.pro.dict.yaml` | `dumps.wikimedia.org/zhwiki` 标题转储 | 中文维基百科词库 |
| `zhwiktionary.pro.dict.yaml` | `dumps.wikimedia.org/zhwiktionary` 标题转储 | 中文维基词典词库 |
| `zhwikisource.pro.dict.yaml` | `dumps.wikimedia.org/zhwikisource` 标题转储 | 中文维基文库词库 |
| `web-slang.pro.dict.yaml` | 维基百科《中国大陆网络用语列表》 | 网络用语词库 |
| `moegirl.pro.dict.yaml` | 萌娘百科 MediaWiki API 标题清单 | 萌娘百科词库 |

## 输出格式示例

处理前（构建产物原始格式）：

```
不能同意更多	bu neng tong yi geng duo
```

处理后（带声调拼音 + 墨奇辅助码）：

```
不能同意更多	bù;kx néng;bq tóng;u yì;pw gèng;a duō;e
```

每个音节的格式为 `声调拼音;辅助码`，词内各音节以空格分隔。

## 构建链路

本项目不生产词库数据，也不再依赖上游发布的词典产物；我们取用上游的**构建代码**，自己对原始数据执行构建：

| 变体 | 原始数据 | 构建工具（构建时克隆最新版） |
|------|----------|------------------------------|
| zhwiki / zhwiktionary / zhwikisource | Wikimedia `all-titles-in-ns0` 转储 | [felixonmars/fcitx5-pinyin-zhwiki](https://github.com/felixonmars/fcitx5-pinyin-zhwiki) 的 Makefile 与 convert.py |
| web-slang | zh.wikipedia.org 页面 wikitext | 同上仓库的 `zhwiki-web-slang.py` |
| moegirl | mobile.moegirl.org.cn MediaWiki API | [outloudvi/mw2fcitx](https://github.com/outloudvi/mw2fcitx) CLI + 其 `pkg-moegirl` 分支的拼音修正表与补充词表 |

辅助码与自定义拼音修正数据来自 [amzxyz/RIME-LMDG](https://github.com/amzxyz/RIME-LMDG)。

> 萌娘百科主站 `zh.moegirl.org.cn` 会拒绝匿名 `list=allpages`，因此默认使用官方 `mobile.moegirl.org.cn` API；若该入口也抓取失败，才回退到 mw2fcitx 最新 Release 的 `titles.txt`。可用 `--no-moegirl-fallback` 禁止回退。

## 使用方法

### 直接下载

1. 前往本仓库的 [Releases](../../releases) 页面
2. 下载所需的 `.pro.dict.yaml` 文件
3. 将文件放入 RIME 用户目录，并在输入方案中引用对应词典名

### 手动构建

前提条件：Python 3.11+、`git`、`make`、`wget`、`gzip`。

```bash
pip install -r requirements.txt

# 1) 构建原始词典（仅重建上游数据有变化的变体）
python build_dicts.py                      # 全部变体
python build_dicts.py --variant web-slang  # 指定变体
python build_dicts.py --dry-run            # 只探测各数据源版本
python build_dicts.py --force              # 忽略构建记录，强制重建

# 2) 加工为 .pro 词典
python process_dict.py raw/web-slang.dict.yaml output/web-slang.pro.dict.yaml
```

常用参数：

| 参数 | 说明 |
|------|------|
| `--raw-dir` / `--work-dir` | 原始产物目录（默认 `raw/`）、上游代码与中间产物目录（默认 `tmp/build/`） |
| `--moegirl-interval-days` | 萌百重建周期，默认 30 天，避免频繁全站抓取 |
| `--moegirl-offline` | 跳过萌百 API，直接使用上游 `titles.txt` |
| `--moegirl-title-limit` | 限制标题数量，用于冒烟测试 |

萌百 API 若限制 GitHub Runner 出口，可设置仓库 Actions Secret `MOEGIRL_PROXY_URL`，
值为 `socks5h://用户名:密码@主机:端口` 或 `http://用户名:密码@主机:端口`。
该代理仅注入萌百 API 抓取子进程；Git、Wikimedia 与 fallback `titles.txt` 下载仍然直连。

`process_dict.py` 会自动从网络下载辅助码数据和自定义拼音修正，无需额外配置，可通过 `--aux-url` 指定自定义辅助码数据源。

## 自动更新机制

GitHub Actions 每日 UTC 02:00 执行（也支持手动触发，可指定变体或强制重建）：

1. **版本探测**：读取 Wikimedia 转储索引取最新可用转储日期；抓取网络用语页面计算内容指纹；萌百按构建周期判断
2. **按需构建**：仅对版本标识发生变化的变体执行构建，其余跳过
3. **加工**：对本次构建出的原始词典逐行生成带声调拼音与辅助码的 `.pro.dict.yaml`
4. **记录持久化**：把各变体的数据版本写入 `versions.json` 并提交，避免重复构建
5. **滚动发布**：向 `latest` Release 覆盖上传本次产物，未重建的变体保留原有资产

`versions.json` 中每个变体记录 `{"id": 数据版本, "built": 构建日期}`：转储日期（维基系列）、页面 wikitext 指纹（web-slang）、标题来源标识（moegirl）。

## 项目结构

```
WanxiangExtra/
├── .github/
│   └── workflows/
│       └── update-dicts.yml    # GitHub Actions 自动构建与发布工作流
├── build_dicts.py              # 构建编排：版本探测 → 调用上游构建 → 产出原始词典
├── dump_index.py               # Wikimedia 转储索引：发现最新可用标题转储
├── upstream.py                 # 上游仓库浅克隆/同步与子进程执行
├── moegirl_config.py           # 萌娘百科的 mw2fcitx 构建配置（仅 RIME 生成器）
├── net.py                      # 统一 User-Agent 的 HTTP 会话与流式下载
├── versions.py                 # 构建记录（versions.json）读写
├── aux_loader.py               # 辅助码数据下载与墨奇码解析
├── pinyin_engine.py            # 带声调拼音生成引擎（含自定义拼音修正）
├── process_dict.py             # 词典加工主程序（流式逐行转换）
├── versions.json               # 各变体的数据版本记录（自动维护）
└── requirements.txt            # Python 依赖
```

## 致谢

- [felixonmars/fcitx5-pinyin-zhwiki](https://github.com/felixonmars/fcitx5-pinyin-zhwiki) — 中文维基系列词库构建脚本
- [outloudvi/mw2fcitx](https://github.com/outloudvi/mw2fcitx) — MediaWiki 词库构建工具与萌百构建配置
- [amzxyz/RIME-LMDG](https://github.com/amzxyz/RIME-LMDG) — 辅助码与自定义拼音数据
- [pypinyin](https://github.com/mozillazg/python-pinyin) — Python 汉字拼音转换工具
- [Wikimedia](https://dumps.wikimedia.org/legal.html) / [萌娘百科](https://zh.moegirl.org.cn/) — 原始词条数据（产物遵循各自的内容许可）
- [RIME](https://rime.im/) — 中州韵输入法引擎
