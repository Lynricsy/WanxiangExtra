# WanxiangExtra

自动化 RIME 词库处理器，为上游开源词库添加带声调拼音与墨奇辅助码，生成可直接部署的 `.pro.dict.yaml` 词典文件。

## 功能特性

- **自动监控上游更新**：通过 GitHub Actions 每日定时检查上游词库仓库的最新 Release，仅在检测到新版本时触发处理流程
- **带声调拼音标注**：使用 pypinyin 引擎为每个汉字生成准确的声调拼音，并集成 RIME-LMDG 自定义拼音修正数据
- **墨奇辅助码附加**：自动下载并解析 RIME-LMDG 辅助码数据，为每个汉字附加墨奇（Moqi）辅助码
- **流式逐行处理**：采用逐行读写的流式架构，避免大文件一次性加载导致的内存问题
- **滚动发布**：处理完成后自动创建 GitHub Release，始终保持一个 `latest` 标签指向最新词典

## 输出文件

| 文件名 | 来源 | 说明 |
|--------|------|------|
| `moegirl.pro.dict.yaml` | [mw2fcitx](https://github.com/outloudvi/mw2fcitx) | 萌娘百科词库 |
| `zhwiki.pro.dict.yaml` | [fcitx5-pinyin-zhwiki](https://github.com/felixonmars/fcitx5-pinyin-zhwiki) | 中文维基百科词库 |
| `zhwiktionary.pro.dict.yaml` | [fcitx5-pinyin-zhwiki](https://github.com/felixonmars/fcitx5-pinyin-zhwiki) | 中文维基词典词库 |
| `zhwikisource.pro.dict.yaml` | [fcitx5-pinyin-zhwiki](https://github.com/felixonmars/fcitx5-pinyin-zhwiki) | 中文维基文库词库 |
| `web-slang.pro.dict.yaml` | [fcitx5-pinyin-zhwiki](https://github.com/felixonmars/fcitx5-pinyin-zhwiki) | 网络用语词库 |

## 输出格式示例

处理前（上游原始格式）：

```
不能同意更多	bu neng tong yi geng duo
```

处理后（带声调拼音 + 墨奇辅助码）：

```
不能同意更多	bù;kx néng;bq tóng;u yì;pw gèng;a duō;e
```

每个音节的格式为 `声调拼音;辅助码`，词内各音节以空格分隔。

## 数据来源

本项目不生产词库数据，仅对上游开源项目的词库进行二次加工：

| 上游项目 | 说明 |
|----------|------|
| [outloudvi/mw2fcitx](https://github.com/outloudvi/mw2fcitx) | 萌娘百科词库生成工具，提供 `moegirl.dict.yaml` |
| [felixonmars/fcitx5-pinyin-zhwiki](https://github.com/felixonmars/fcitx5-pinyin-zhwiki) | 中文维基系列拼音词库，提供 zhwiki、zhwiktionary、zhwikisource、web-slang 四个变体 |
| [amzxyz/RIME-LMDG](https://github.com/amzxyz/RIME-LMDG) | 辅助码数据（墨奇等多种方案）与自定义拼音修正数据 |

## 使用方法

### 直接下载

1. 前往本仓库的 [Releases](../../releases) 页面
2. 下载所需的 `.pro.dict.yaml` 文件
3. 将文件放入 RIME 用户目录，并在输入方案中引用对应词典名

### 手动运行

前提条件：Python 3.11+，已安装依赖。

```bash
pip install -r requirements.txt
python process_dict.py input.dict.yaml output.pro.dict.yaml
```

`process_dict.py` 会自动从网络下载辅助码数据和自定义拼音修正，无需额外配置。可通过 `--aux-url` 参数指定自定义辅助码数据源。

## 自动更新机制

本项目通过 GitHub Actions 实现全自动的词库更新流程：

1. **定时触发**：每日 UTC 02:00 执行定时任务（也支持手动触发，可选强制更新模式）
2. **版本检测**：通过 GitHub API 获取上游仓库最新 Release 的 tag，与本地 `versions.json` 中记录的版本号比对
3. **按需处理**：仅当检测到上游版本变化时，才执行下载、处理和发布流程
4. **版本持久化**：处理完成后将新版本号写入 `versions.json` 并提交到仓库，确保下次检查时不会重复处理
5. **滚动发布**：删除旧的 `latest` Release 后重新创建，始终保持单一最新版本

## 项目结构

```
WanxiangExtra/
├── .github/
│   └── workflows/
│       └── update-dicts.yml    # GitHub Actions 自动更新工作流
├── aux_loader.py               # 辅助码数据下载与墨奇码解析
├── pinyin_engine.py            # 带声调拼音生成引擎（含自定义拼音修正）
├── process_dict.py             # 词典处理主程序（流式逐行转换）
├── version_checker.py          # 上游版本检测与文件下载
├── versions.json               # 本地版本记录（自动维护）
└── requirements.txt            # Python 依赖：pypinyin, pyyaml, requests
```

## 致谢

- [outloudvi/mw2fcitx](https://github.com/outloudvi/mw2fcitx) — 萌娘百科词库
- [felixonmars/fcitx5-pinyin-zhwiki](https://github.com/felixonmars/fcitx5-pinyin-zhwiki) — 中文维基系列词库
- [amzxyz/RIME-LMDG](https://github.com/amzxyz/RIME-LMDG) — 辅助码与自定义拼音数据
- [pypinyin](https://github.com/mozillazg/python-pinyin) — Python 汉字拼音转换工具
- [RIME](https://rime.im/) — 中州韵输入法引擎
