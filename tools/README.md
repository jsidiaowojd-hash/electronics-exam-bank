# tools/ —— 题库站构建流水线

仓库根目录里的历年真题 PDF，会在 GitHub Actions 里自动加工成结构化的题库站点
（逐题网页 + 答案/解析 + 知识点标签 + JSON 接口 + llms.txt）。

## 三个阶段

1. `ingest.py` —— PDF 入库：去水印、抽逐页文本、抽题目配图（优先用 PDF 内嵌位图）、
   生成整页渲染图。产出 `data/papers/*.json`。
2. `parse.py` —— 切题：把逐页文本切成一道一道的题，接上答案解析，打知识点标签。
   产出 `data/questions/*.json`。
3. `build.py` —— 建站：生成首页、试卷页、知识点页、搜索页、`api/*.json`、
   `llms.txt`、`llms-full.txt`、`sitemap.xml`、`openapi.yaml`。

配套脚本：

* `watermark.py` —— 从 PDF 内容流里摘掉水印文字对象（正文与矢量图不受影响）。
* `check.py` —— 站点自检：断链、素材、JSON 接口完整性。
* `peek.py` —— 快速浏览某份试卷切成了什么样，便于人工校对。
* `export_bundle.py` —— 把全量题目导成单个 Markdown，直接丢给 ChatGPT。
* `mcp_server.py` —— MCP 服务端，让支持 MCP 的客户端直接查题。

## 本地复现

```bash
python tools/ingest.py --pdf-root . --out build/data --site build/public
python tools/parse.py --data build/data
python tools/build.py --data build/data --site build/public --site-url <你的站点地址>
python tools/check.py --site build/public
```

## 人工校对

自动切题不可能 100% 准确（各校题号写法不同，答案部分有的重新编号），
`data/questions/*.json` 是干净的 JSON，可以直接手改，改完重新构建即可。
每条题目的 `confidence` 字段标出了切分可靠程度。
