# 数模电考研真题库（模拟电子技术 + 数字电子技术）

历年考研真题的**结构化题库站点**：每道题一张卡片（题干、电路图、选项、答案解析、
知识点标签），并提供机器可读接口，方便 ChatGPT 这类模型直接检索。

站点：https://jsidiaowojd-hash.github.io/electronics-exam-bank/

## 内容怎么来的

仓库根目录放的是原始真题 PDF。每次 push，GitHub Actions 会自动：

1. 抽掉 PDF 里的水印文字对象（正文和电路图不动）；
2. 抽出逐页文本、题目配图（优先用 PDF 内嵌位图）、整页原图；
3. 把文本切成一道一道的题，接上答案与解析，打上知识点标签；
4. 生成网站：首页、试卷页、知识点页、搜索页，以及 `llms.txt`、`api/*.json`。

所以**加新卷子只需要把 PDF 丢进仓库根目录并 push**，不需要手工做图或写网页。

## 站点结构

| 地址 | 说明 |
| --- | --- |
| `/` | 首页：试卷卡片 + 常考知识点 + 给模型用的入口 |
| `/paper/<slug>/` | 每道题一张卡片，含「查看原文」跳到原卷页 |
| `/tag/<知识点>/` | 按知识点跨试卷聚合（负反馈、卡诺图、振荡电路 …） |
| `/search/` | 纯前端搜索，即输即出 |
| `/pdf/` | 原卷按页阅读（早期版本保留） |
| `/llms.txt` | 给大模型看的内容清单 |
| `/llms-full.txt` | 全量题目纯文本 |
| `/api/papers.json`、`/api/questions.json` | 结构化 JSON 接口 |
| `/openapi.yaml` | Custom GPT Actions 用的接口定义 |

## 让 ChatGPT 直接查题

把下面任一地址贴给开了联网的 ChatGPT：

```
https://jsidiaowojd-hash.github.io/electronics-exam-bank/llms.txt
```

或者本地挂 MCP（`tools/mcp_server.py`），直接问「2024 中大 885 第 7 题为什么选 A」。

## 数据可靠性说明

每题都带 `confidence` 字段：`high`（题干+选项+答案齐）、`medium`（缺答案或选项）、
`low`（只切出题干）。`low`/`medium` 的题在网页上显示「待校对」角标。
校对方式是直接改 `data/questions/*.json`（由 CI 生成，可在本地生成后提交）。

## 版权

真题版权归各招生单位；答案与解析版权归原作者。本仓库整理自公开流传的资料，
仅供个人复习使用，请勿用于商业用途；权利人如有异议，联系后会立即下线。
