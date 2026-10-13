#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把结构化题库 data/questions/*.json 生成为静态站点 site/。

生成内容：
  * 首页、试卷页、知识点（标签）页、客户端搜索页
  * /api/*.json        给 ChatGPT 之类的外部程序直接抓取的结构化接口
  * /llms.txt + /llms-full.txt  让大模型一眼看懂站点内容的清单
  * /sitemap.xml /robots.txt    搜索引擎收录
  * /openapi.yaml              配 Custom GPT Actions 用的接口描述
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
from pathlib import Path

from PIL import Image

SITE_NAME = "数模电考研真题库"
SITE_TAGLINE = "模拟电子技术 + 数字电子技术 考研真题、答案与解析"
SITE_URL = "https://example.com"  # 部署后改成自己的域名，或用 --site-url / SITE_URL 环境变量覆盖
INDEX_VERSION = "question-index-v2"
INDEX_UPDATED_AT = "2026-10-13 (Asia/Shanghai)"


def q_url(qid: str) -> str:
    """稳定的单题地址：/question/<question_id>.html"""
    return f"{SITE_URL}/question/{qid}.html"

CSS = """
:root{--bg:#f7f8fa;--card:#fff;--ink:#1c2128;--muted:#6b7683;--line:#e5e8ee;
--brand:#2f6df6;--brand-soft:#eef3ff;--ok:#1a8a5a;--warn:#c47f00}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-size:16px;line-height:1.7;
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB",
"Microsoft YaHei",sans-serif}
a{color:var(--brand);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:960px;margin:0 auto;padding:0 18px}
header.top{background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:10}
header.top .wrap{display:flex;align-items:center;gap:14px;height:58px}
.brand{font-weight:700;font-size:17px}
nav.top a{color:var(--muted);font-size:14px;margin-right:14px}
h1{font-size:26px;margin:26px 0 6px}
h2{font-size:20px;margin:34px 0 12px;padding-left:10px;border-left:4px solid var(--brand)}
.sub{color:var(--muted);font-size:14px;margin:0 0 18px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.card h3{margin:0 0 6px;font-size:17px}
.meta{color:var(--muted);font-size:13px}
.q{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin:16px 0}
.q-head{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
.q-no{font-weight:700;color:var(--brand)}
.pill{font-size:12px;padding:1px 9px;border-radius:999px;background:var(--brand-soft);color:#2b4bb5}
.pill.gray{background:#f0f2f5;color:var(--muted)}
.pill.warn{background:#fff5e2;color:var(--warn)}
.pill.reviewed-stem{background:#eef3ff;color:#2b4bb5}
.pill.reviewed-full{background:#e6f6ec;color:#1a8a5a}
.stem{white-space:pre-wrap}
.options{margin:10px 0 0;padding:0;list-style:none}
.options li{padding:5px 0;display:flex;gap:8px}
.options .lab{font-weight:700;color:var(--muted);min-width:18px}
figure{margin:12px 0}
figure img{max-width:100%;border:1px solid var(--line);border-radius:8px;background:#fff;display:block;margin:0 auto}
figcaption{font-size:12px;color:var(--muted);text-align:center;margin-top:6px}
details{margin-top:12px;border-top:1px dashed var(--line);padding-top:10px}
summary{cursor:pointer;color:var(--brand);font-size:14px;font-weight:600}
.answer{margin-top:10px;background:#fafbfd;border:1px solid var(--line);border-radius:8px;padding:12px}
.answer b{color:var(--ok)}
.ans-src{margin:12px 0 4px}
.ans-src img{width:100%;border:1px solid var(--line);border-radius:6px;background:#fff}
.ans-src figcaption{font-size:12px;color:var(--muted);text-align:left;margin-top:4px}
.source-question{margin:14px 0}
.source-question a{display:block}
.source-question img{width:100%;cursor:zoom-in}
.source-question figcaption{text-align:left}
.text-note{margin:10px 0;background:#fff8e6;border:1px solid #f0dca8;border-radius:8px;padding:9px 11px;color:#6a5320;font-size:13px}
.text-ver{margin-top:10px;border-top:1px dotted var(--line);padding-top:8px}
.text-ver summary{font-weight:500;color:var(--muted);font-size:13px}
sub,sup{font-size:.72em}
.q figure img{cursor:zoom-in}
.explain{white-space:pre-wrap;color:#333a44;font-size:15px}
.tags{margin-top:10px;display:flex;gap:8px;flex-wrap:wrap}
.tag{font-size:12px;background:#f0f2f5;color:#4a5563;border-radius:999px;padding:2px 10px}
.searchbox{width:100%;padding:12px 14px;border:1px solid var(--line);border-radius:10px;font-size:15px}
.result{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin:10px 0}
.mark{background:#fff3bf}
footer{margin:50px 0 30px;color:var(--muted);font-size:13px;text-align:center}
.toc{columns:2;font-size:14px}
.qnav{display:flex;gap:14px;flex-wrap:wrap;margin:16px 0;font-size:14px}
.stars{color:#e8a33d;letter-spacing:2px}
.progress b{display:block;margin-bottom:8px}
.done-btn,.export-btn{margin:0 8px 8px 0;padding:7px 14px;border:1px solid var(--line);border-radius:8px;background:#fff;font-size:14px;cursor:pointer}
.done-btn.is-done{background:var(--brand-soft);border-color:#c7d7ff;color:#2b4bb5}
.export-btn{background:#f7f8fa}
.q-no{text-decoration:none}
.pill.done-badge{background:#e6f6ec;color:#1a8a5a}
@media (max-width:640px){.toc{columns:1}}
.admon{background:#fff8e6;border:1px solid #f0dca8;border-radius:10px;padding:12px 14px;font-size:14px;color:#6a5320}
"""

JS = """
// ---- 做题进度：只存在浏览器本地，可导出为 JSON 贴给模型 ----
const DONE_KEY = 'kaoyan-done-v1';
function doneSet(){ try { return new Set(JSON.parse(localStorage.getItem(DONE_KEY) || '[]')); } catch(e){ return new Set(); } }
function saveDone(s){ localStorage.setItem(DONE_KEY, JSON.stringify([...s])); }
function paintDone(){
  const s = doneSet();
  document.querySelectorAll('[data-qid]').forEach(el=>{
    const id = el.getAttribute('data-qid');
    if (el.classList.contains('done-btn')) {
      el.textContent = s.has(id) ? '✓ 已做（点击取消）' : '标记为已做';
      el.classList.toggle('is-done', s.has(id));
      return;
    }
    if (s.has(id) && !el.querySelector('.done-badge')) {
      const b = document.createElement('span'); b.className = 'pill done-badge'; b.textContent = '✓ 已做';
      (el.querySelector('.q-head') || el).appendChild(b);
    }
  });
}
document.addEventListener('click', e=>{
  const btn = e.target.closest('.done-btn');
  if (btn) { const s = doneSet(); const id = btn.getAttribute('data-qid');
    s.has(id) ? s.delete(id) : s.add(id); saveDone(s); paintDone(); return; }
  const exp = e.target.closest('.export-btn');
  if (exp) { const txt = JSON.stringify([...doneSet()], null, 1);
    navigator.clipboard.writeText(txt).then(()=>{ exp.textContent = `已复制 ${JSON.parse(txt).length} 条`; },
      ()=>{ window.prompt('复制下面的内容发给 ChatGPT：', txt); }); }
});

// 题库搜索：把 search-index.json 拉下来做前端检索
async function initSearch(){
  const box=document.getElementById('q');
  const out=document.getElementById('out');
  if(!box) return;
  const idx=await (await fetch(SEARCH_INDEX_URL)).json();
  const render=(kw)=>{
    const terms=kw.toLowerCase().split(/\\s+/).filter(Boolean);
    if(!terms.length){out.innerHTML='<p class="meta">输入关键词，例如：共射放大电路、卡诺图、负反馈、2024 中山大学</p>';return;}
    const scored=idx.map(it=>{
      const hay=(it.title+' '+it.text+' '+it.tags.join(' ')).toLowerCase();
      let s=0;terms.forEach(t=>{const c=hay.split(t).length-1;if(c)s+=c;if(it.title.toLowerCase().includes(t))s+=3;});
      return {it,s};
    }).filter(x=>x.s>0).sort((a,b)=>b.s-a.s).slice(0,40);
    out.innerHTML=scored.map(({it})=>`<div class="result"><div class="meta">${it.paper}</div>
      <div><a href="${it.url}">${it.title}</a></div>
      <div class="meta">${it.tags.join(' · ')}</div>
      <div>${it.text.slice(0,180)}</div></div>`).join('')||'<p class="meta">没有匹配的题目</p>';
  };
  box.addEventListener('input',()=>render(box.value));
  render('');
}
document.addEventListener('DOMContentLoaded',initSearch);
document.addEventListener('DOMContentLoaded',paintDone);
"""


def esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def fmt_math(text: str) -> str:
    """先转义，再把 _{...} / ^{...} 变成真正的上下标。"""
    out = esc(text)
    out = re.sub(r"\^\{([^{}]{1,40})\}", r"<sup>\1</sup>", out)
    out = re.sub(r"_\{([^{}]{1,40})\}", r"<sub>\1</sub>", out)
    return out


def tag_slug(tag: str) -> str:
    """知识点名里可能有 / 之类的字符，转成安全的目录名。"""
    return re.sub(r"[/\\?#%]+", "-", tag).strip("-") or "misc"


def render_layout(title: str, body: str, depth: int, extra_head: str = "") -> str:
    rel = "../" * depth
    return f"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} | {SITE_NAME}</title>
<meta name="description" content="{esc(SITE_TAGLINE)}">
<link rel="stylesheet" href="{rel}assets/style.css">
<link rel="alternate" type="application/json" href="{rel}api/papers.json">
{extra_head}
</head><body>
<header class="top"><div class="wrap">
  <a class="brand" href="{rel}index.html">{SITE_NAME}</a>
  <nav class="top">
    <a href="{rel}index.html">首页</a>
    <a href="{rel}search/index.html">搜索</a>
    <a href="{rel}llms.txt">llms.txt</a>
    <a href="{rel}api/papers.json">API</a>
  </nav>
</div></header>
<main class="wrap">
{body}
</main>
<footer class="wrap">
  <p>{SITE_NAME} · 内容来自用户整理的历年真题 PDF，仅供个人复习使用。</p>
  <p>结构化数据：<a href="{rel}api/papers.json">/api/papers.json</a> ·
     <a href="{rel}api/questions.json">/api/questions.json</a> ·
     <a href="{rel}llms-full.txt">/llms-full.txt</a></p>
</footer>
<script src="{rel}assets/app.js"></script>
</body></html>
"""


def paper_title(paper: dict) -> str:
    school = paper.get("school") or "某高校"
    code = paper.get("code") or ""
    year = paper.get("year")
    ytxt = f"{year} 年" if year else "近年"
    return f"{school} {code} 电子技术 {ytxt}真题及答案解析".replace("  ", " ").strip()


def question_html(q: dict, depth: int, slug: str) -> str:
    rel = "../" * depth
    parts = ['<div class="q" id="%s" data-qid="%s">' % (q["id"], q["id"])]
    head = [
        f'<a class="q-no" href="{rel}question/{q["id"]}.html" '
        f'title="这一题的独立链接">{q["number"]}.</a>'
    ]
    if q.get("section"):
        head.append(f'<span class="pill">{esc(q["section"])}</span>')
    if q.get("part"):
        head.append(f'<span class="pill gray">{esc(q["part"][:22])}</span>')
    review_status = q.get("review_status") or "未校对"
    review_class = {
        "未校对": "warn",
        "题干已校对": "reviewed-stem",
        "解析已校对": "reviewed-full",
    }.get(review_status, "warn")
    head.append(f'<span class="pill {review_class}">{esc(review_status)}</span>')
    head.append(
        f'<a class="meta" style="margin-left:auto" href="{rel}assets/pages/{slug}/p{q["page"]:02d}.png"'
        ' target="_blank">查看原文</a>'
    )
    parts.append('<div class="q-head">' + "".join(head) + "</div>")
    parts.append(f'<div class="stem">{fmt_math(q["stem"])}</div>')
    if q.get("text_note"):
        parts.append(f'<div class="text-note">{esc(q["text_note"])}</div>')
    for i, source_img in enumerate(q.get("source_images", [])):
        parts.append(
            f'<figure class="source-question"><a href="{rel}{source_img}" target="_blank" '
            f'title="打开原尺寸"><img src="{rel}{source_img}" '
            f'alt="第 {q["number"]} 题完整原题裁图 {i + 1}" loading="lazy"></a>'
            f'<figcaption>完整原题裁图（{i + 1}/{len(q["source_images"])}）· 点击放大 · '
            "公式与异常字符以此图为准</figcaption></figure>"
        )
    for i, fig in enumerate(q.get("figures", [])):
        parts.append(
            f'<figure><img src="{rel}{fig}" alt="第 {q["number"]} 题配图 {i + 1}" loading="lazy">'
            f'<figcaption>第 {q["number"]} 题 图 {i + 1}</figcaption></figure>'
        )
    if q.get("options"):
        parts.append('<ul class="options">')
        for opt in q["options"]:
            parts.append(
                f'<li><span class="lab">{esc(opt["label"])}</span>'
                f'<span>{fmt_math(opt["text"]) or "（见图）"}</span></li>'
            )
        parts.append("</ul>")
    if q.get("answer") or q.get("explanation") or q.get("answer_imgs"):
        parts.append("<details><summary>查看答案与解析</summary><div class=\"answer\">")
        parts.append(f'<b>正确答案：{fmt_math(q.get("answer") or "见解析")}</b>')
        for i, img in enumerate(q.get("answer_imgs", [])):
            parts.append(
                f'<figure class="ans-src"><img src="{rel}{img}" alt="解析原图 {i + 1}" loading="lazy">'
                f'<figcaption>原卷解析（{i + 1}/{len(q["answer_imgs"])}）'
                "· 排版复杂的公式以原图为准</figcaption></figure>"
            )
        if q.get("explanation"):
            parts.append(
                "<details class=\"text-ver\"><summary>文字版（供复制与检索，公式可能不完整）</summary>"
                f'<div class="explain">{fmt_math(q.get("explanation"))}</div></details>'
            )
        parts.append("</div></details>")
    if q.get("tags"):
        parts.append('<div class="tags">')
        for tag in q["tags"]:
            parts.append(
                f'<a class="tag" href="{rel}tag/{esc(tag_slug(tag))}/index.html">{esc(tag)}</a>'
            )
        parts.append("</div>")
    parts.append("</div>")
    return "".join(parts)


def question_page(paper: dict, q: dict, prev_q: dict | None, next_q: dict | None) -> str:
    """单题页面：稳定 URL /question/<id>.html，便于模型与搜索引擎单独引用。"""
    title = f"{paper_title(paper)} 第 {q['number']} 题"
    rel = "../"
    bits = [esc(paper_title(paper))]
    if q.get("section"):
        bits.append(esc(q["section"]))
    if q.get("difficulty_stars"):
        bits.append(f'难度 <span class="stars">{esc(q["difficulty_stars"])}</span>')
    else:
        bits.append("难度未标注")
    if q.get("tags"):
        bits.append("知识点：" + "、".join(esc(t) for t in q["tags"]))

    body = [
        f'<h1>第 {q["number"]} 题</h1>',
        '<p class="sub">' + " · ".join(bits) + "</p>",
        '<div class="admon">题目 ID：<code>' + esc(q["id"]) + "</code> ｜ "
        f'<a href="{rel}paper/{paper["slug"]}/index.html#{esc(q["id"])}">在整卷中查看</a> ｜ '
        f'<a href="{rel}api/questions/{paper["slug"]}.json">这份卷子的 JSON</a></div>',
        question_html({**q, "figures": q.get("figures", []), "answer_imgs": q.get("answer_imgs", [])}, 1, paper["slug"]),
        '<div class="qnav">',
    ]
    if prev_q:
        body.append(
            f'<a href="{rel}question/{prev_q["id"]}.html">← 上一题（第 {prev_q["number"]} 题）</a>'
        )
    body.append(f'<a href="{rel}paper/{paper["slug"]}/index.html">回到整卷</a>')
    if next_q:
        body.append(
            f'<a href="{rel}question/{next_q["id"]}.html">下一题（第 {next_q["number"]} 题）→</a>'
        )
    body.append("</div>")
    body.append(
        '<div class="card progress"><b>做题进度（只存在你这台设备上）</b>'
        f'<button class="done-btn" data-qid="{esc(q["id"])}">标记为已做</button>'
        '<button class="export-btn">复制我做过的题（JSON）</button>'
        '<div class="meta">把复制出来的内容贴给 ChatGPT，它就知道哪些题你练过了。</div></div>'
    )

    desc = re.sub(r"\s+", " ", q.get("stem", ""))[:110]
    if q.get("answer"):
        desc += f' 答案：{q["answer"]}'
    extra = (
        f'<link rel="canonical" href="{q_url(q["id"])}">\n'
        f'<meta property="og:type" content="article">\n'
        f'<meta property="og:title" content="{esc(title)}">\n'
        f'<meta property="og:description" content="{esc(desc)}">\n'
        f'<script type="application/ld+json">{json.dumps(_quiz_ld(paper, q), ensure_ascii=False)}</script>'
    )
    return render_layout(title, "\n".join(body), 1, extra)


def _quiz_ld(paper: dict, q: dict) -> dict:
    ld = {
        "@context": "https://schema.org",
        "@type": "Question",
        "name": f'{paper_title(paper)} 第 {q["number"]} 题',
        "text": q.get("stem", ""),
        "url": q_url(q["id"]),
        "identifier": q["id"],
        "about": [{"@type": "Thing", "name": t} for t in q.get("tags", [])],
    }
    if q.get("answer"):
        ld["acceptedAnswer"] = {"@type": "Answer", "text": q["answer"]}
    return ld


def md_to_html(text: str) -> str:
    """把选题索引这份结构简单的 Markdown 转成 HTML（只用到标题、列表、链接）。"""
    out, in_list = [], False
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("### "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h3>{esc(line[4:])}</h3>")
        elif line.startswith("## "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h2>{esc(line[3:])}</h2>")
        elif line.startswith("# "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h1>{esc(line[2:])}</h1>")
        elif line.startswith("- "):
            if not in_list:
                out.append('<ul class="idx">')
                in_list = True
            item = esc(line[2:])
            item = re.sub(
                r"(https?://[^\s<]+)",
                r'<a href="\1">\1</a>',
                item,
            )
            item = item.replace("**", "")
            out.append(f"<li>{item}</li>")
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<p>{esc(line)}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def band_crop(site_dir: Path, paper: dict, q: dict) -> str | None:
    """扫描版试卷：按题目在版面上的纵向范围从整页图里裁出原文图。"""
    size = paper.get("page_size") or {}
    pw, ph = size.get("width"), size.get("height")
    if not pw or not ph or q.get("y_top") is None:
        return None
    src = site_dir / "assets" / "pages" / paper["slug"] / f"p{q['page']:02d}.png"
    if not src.exists():
        return None
    out_rel = f"assets/figs/{paper['slug']}/q{q['number']:02d}-text.png"
    out = site_dir / out_rel
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        try:
            im = Image.open(src)
            scale = im.width / float(pw)
            top = max(0, int((q["y_top"] - 6) * scale))
            bottom = min(im.height, int((q["y_bottom"] + 8) * scale))
            if bottom - top < 35:
                return None
            im.crop((0, top, im.width, bottom)).save(out)
        except Exception:
            return None
    return out_rel


def answer_crop(site_dir: Path, paper: dict, q: dict, idx: int, block: dict) -> str | None:
    """把解析在版面上的原始排版裁出来——分式、上下标、上划线只有原图才看得清。"""
    size = paper.get("page_size") or {}
    pw = size.get("width")
    if not pw:
        return None
    src = site_dir / "assets" / "pages" / paper["slug"] / f"p{int(block['page']):02d}.png"
    if not src.exists():
        return None
    out_rel = f"assets/answer-source/{q['id']}-ans{idx:02d}.png"
    out = site_dir / out_rel
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        return out_rel
    try:
        im = Image.open(src)
        scale = im.width / float(pw)
        top = max(0, int((block["top"] - 8) * scale))
        bottom = min(im.height, int((block["bottom"] + 8) * scale))
        if bottom - top < 30:
            return None
        im.convert("L").crop((0, top, im.width, bottom)).save(out, optimize=True)
    except Exception:
        return None
    return out_rel


def build(data_dir: Path, site_dir: Path) -> dict:
    q_dir = data_dir / "questions"
    all_papers = []
    for path in sorted(q_dir.glob("*.json")):
        if path.name == "index.json":
            continue
        all_papers.append(json.loads(path.read_text(encoding="utf-8")))
    all_papers.sort(key=lambda p: (-(p.get("year") or 0), p.get("slug", "")))
    # 切出题目的卷子正常建站；纯扫描件（0 题）只做「原卷逐页翻阅」页
    papers = [p for p in all_papers if p.get("stats", {}).get("total", 0) > 0]
    browse_only = [p for p in all_papers if p.get("stats", {}).get("total", 0) == 0]
    papers.sort(key=lambda p: (-(p.get("year") or 0), p.get("slug", "")))
    (site_dir / "assets").mkdir(parents=True, exist_ok=True)
    (site_dir / "assets" / "style.css").write_text(CSS.strip(), encoding="utf-8")
    (site_dir / "assets" / "app.js").write_text(JS.strip(), encoding="utf-8")

    search_index, all_questions, tag_map = [], [], {}
    cards = []
    for paper in papers:
        slug = paper["slug"]
        title = paper_title(paper)
        depth = 2  # site/paper/<slug>/index.html
        rel = "../../"
        stats = paper.get("stats", {})
        if paper.get("scan_style"):
            for q in paper["questions"]:
                if not q.get("figures"):
                    band = band_crop(site_dir, paper, q)
                    if band:
                        q["figures"] = [band]
        for q in paper["questions"]:
            # 校对状态与自动抽取置信度相互独立；未进入人工校准流程的题目一律显式标记。
            q.setdefault("review_status", "未校对")
            imgs = []
            for i, block in enumerate(q.get("answer_blocks", []), start=1):
                rel_img = answer_crop(site_dir, paper, q, i, block)
                if rel_img:
                    imgs.append(rel_img)
            q["answer_imgs"] = imgs
        body = [f"<h1>{esc(title)}</h1>"]
        body.append(
            f'<p class="sub">共 {stats.get("total", 0)} 题 · '
            f'收录答案 {stats.get("with_answer", 0)} 题 · '
            f'解析 {stats.get("with_explanation", 0)} 题 · '
            f'配图 {stats.get("with_figure", 0)} 处 · '
            f'原卷 {paper.get("page_count", 0)} 页'
            + (f' · {esc(paper["clean_note"])}' if paper.get("clean_note") else "")
            + "</p>"
        )
        toc = []
        for q in paper["questions"]:
            num = q["number"]
            toc.append(
                f'<div><a href="#{q["id"]}">{num}. {fmt_math(q["stem"][:38])}</a></div>'
            )
        if toc:
            body.append('<div class="card toc">' + "".join(toc) + "</div>")
        sections_seen = []
        for q in paper["questions"]:
            key = (q.get("part"), q.get("section"))
            if key not in sections_seen:
                sections_seen.append(key)
                label = " · ".join(x for x in key if x) or "试题"
                body.append(f"<h2>{esc(label)}</h2>")
            body.append(question_html(q, depth, slug))
            search_index.append(
                {
                    "url": f"question/{q['id']}.html",
                    "paper_url": f"paper/{slug}/index.html#{q['id']}",
                    "title": f"{title} 第 {q['number']} 题",
                    "qid": q["id"],
                    "paper": title,
                    "slug": slug,
                    "number": q["number"],
                    "tags": q.get("tags", []),
                    "text": (q.get("stem", "") + " " + " ".join(o["text"] for o in q.get("options", []))
                             + " " + (q.get("answer") or "")),
                }
            )
            all_questions.append(
                {"paper": title, "slug": slug, "question_url": q_url(q["id"]), **q}
            )
            for tag in q.get("tags", []):
                tag_map.setdefault(tag, []).append((slug, title, q))
        (site_dir / "paper" / slug).mkdir(parents=True, exist_ok=True)
        (site_dir / "paper" / slug / "index.html").write_text(
            render_layout(title, "\n".join(body), depth), encoding="utf-8"
        )
        # 每道题生成一个独立页面
        (site_dir / "question").mkdir(parents=True, exist_ok=True)
        qs = paper["questions"]
        for i, q in enumerate(qs):
            prev_q = qs[i - 1] if i > 0 else None
            next_q = qs[i + 1] if i + 1 < len(qs) else None
            (site_dir / "question" / f"{q['id']}.html").write_text(
                question_page(paper, q, prev_q, next_q), encoding="utf-8"
            )
        cards.append(
            f'<a class="card" href="paper/{slug}/index.html"><h3>{esc(title)}</h3>'
            f'<div class="meta">{stats.get("total", 0)} 题 · 答案 {stats.get("with_answer", 0)} · '
            f'原卷 {paper.get("page_count", 0)} 页</div></a>'
        )

    # ---------- 纯扫描件：原卷逐页翻阅 ----------
    browse_cards = []
    for paper in browse_only:
        slug = paper["slug"]
        title = paper_title(paper)
        pages = []
        for n in range(1, int(paper.get("page_count") or 0) + 1):
            rel_img = f"assets/pages/{slug}/p{n:02d}.png"
            if (site_dir / rel_img).exists():
                pages.append(
                    f'<figure><img src="../../{rel_img}" alt="第 {n} 页" loading="lazy">'
                    f'<figcaption>第 {n} 页</figcaption></figure>'
                )
        body = [
            f"<h1>{esc(title)}</h1>",
            '<p class="sub">这份 PDF 整页是扫描图、没有文字层，暂时切不出题目，'
            "先按原卷逐页翻阅（已自动去掉水印）。</p>",
            "".join(pages) or '<p class="sub">原卷图片缺失。</p>',
        ]
        (site_dir / "paper" / slug).mkdir(parents=True, exist_ok=True)
        (site_dir / "paper" / slug / "index.html").write_text(
            render_layout(title, "\n".join(body), 2), encoding="utf-8"
        )
        browse_cards.append(
            f'<a class="card" href="paper/{slug}/index.html"><h3>{esc(title)}</h3>'
            f'<div class="meta">扫描件 · 原卷 {paper.get("page_count", 0)} 页 · 暂未切题</div></a>'
        )

    # ---------- 知识点页 ----------
    for tag, entries in sorted(tag_map.items()):
        body = [f"<h1>知识点：{esc(tag)}</h1>",
                f'<p class="sub">共 {len(entries)} 道相关题目，来自 {len({e[0] for e in entries})} 份试卷。</p>']
        for slug, title, q in entries:
            body.append(
                f'<div class="q"><div class="q-head"><span class="q-no">{q["number"]}.</span>'
                f'<span class="pill gray">{esc(title)}</span></div>'
                f'<div class="stem">{fmt_math(q["stem"][:200])}</div>'
                f'<div class="tags"><a class="tag" href="../../paper/{slug}/index.html#q{q["number"]}">'
                "去原卷看答案</a></div></div>"
            )
        (site_dir / "tag" / tag_slug(tag)).mkdir(parents=True, exist_ok=True)
        (site_dir / "tag" / tag_slug(tag) / "index.html").write_text(
            render_layout(f"知识点 {tag}", "\n".join(body), 2), encoding="utf-8"
        )

    # ---------- 首页 ----------
    total_q = sum(p.get("stats", {}).get("total", 0) for p in papers)
    total_a = sum(p.get("stats", {}).get("with_answer", 0) for p in papers)
    body = [
        f"<h1>{SITE_NAME}</h1>",
        f'<p class="sub">{esc(SITE_TAGLINE)} · 已收录 {len(papers)} 份试卷 / {total_q} 道题 / '
        f"其中 {total_a} 题带答案与解析。</p>",
        '<div class="admon">本站内容整理自公开流传的历年真题 PDF。真题版权归各招生单位，'
        "解析版权归原作者；请勿用于商业用途，若权利人提出异议会立即下线。</div>",
        "<h2>按试卷浏览</h2>",
        '<div class="grid">' + "".join(cards) + "</div>",
    ]
    if browse_cards:
        body.append("<h2>只有原卷、暂未切题（扫描件）</h2>")
        body.append(
            f'<p class="sub">下面 {len(browse_cards)} 份 PDF 整页是扫描图、没有文字层，'
            "目前提供去水印后的原卷逐页翻阅；想要题目化，需要先做 OCR。</p>"
        )
        body.append('<div class="grid">' + "".join(browse_cards) + "</div>")
    if tag_map:
        tops = sorted(tag_map.items(), key=lambda kv: -len(kv[1]))[:24]
        body.append("<h2>常考知识点</h2>")
        body.append('<div class="card">' + " ".join(
            f'<a class="tag" href="tag/{esc(tag_slug(t))}/index.html">{esc(t)}（{len(v)}）</a>'
            for t, v in tops
        ) + "</div>")
    body.append("<h2>给 ChatGPT 用的入口</h2>")
    body.append(
        '<div class="card"><p>把下面任一地址丢给 ChatGPT（联网/浏览模式）或自建 Agent，'
        "它就能直接读到全站题目：</p><ul>"
        f'<li><code>{SITE_URL}/llms.txt</code> — 站点内容清单</li>'
        f'<li><code>{SITE_URL}/llms-full.txt</code> — 全量题目纯文本</li>'
        f'<li><code>{SITE_URL}/api/questions.json</code> — 全部题目结构化 JSON</li>'
        f'<li><code>{SITE_URL}/api/papers.json</code> — 试卷清单</li>'
        f'<li><code>{SITE_URL}/openapi.yaml</code> — Custom GPT Actions 用的接口定义</li>'
        "</ul></div>"
    )
    (site_dir / "index.html").write_text(
        render_layout(SITE_NAME, "\n".join(body), 0), encoding="utf-8"
    )

    # ---------- 搜索页 ----------
    (site_dir / "search").mkdir(parents=True, exist_ok=True)
    body = [
        "<h1>题库搜索</h1>",
        '<p class="sub">支持题目文字、答案、知识点、学校年份的关键词检索，结果本地匹配、即输即出。</p>',
        '<input id="q" class="searchbox" placeholder="共射放大电路 / 卡诺图 / 负反馈 / 2024 中山大学">',
        '<div id="out"></div>',
        "<script>const SEARCH_INDEX_URL='../api/search-index.json';</script>",
    ]
    (site_dir / "search" / "index.html").write_text(
        render_layout("题库搜索", "\n".join(body), 1), encoding="utf-8"
    )

    # ---------- 接口与给大模型的清单 ----------
    api = site_dir / "api"
    api.mkdir(parents=True, exist_ok=True)
    papers_meta = [
        {
            "slug": p["slug"],
            "school": p.get("school"),
            "code": p.get("code"),
            "year": p.get("year"),
            "title": paper_title(p),
            "page_count": p.get("page_count"),
            "questions": p.get("stats", {}).get("total", 0),
            "with_answer": p.get("stats", {}).get("with_answer", 0),
            "url": f"{SITE_URL}/paper/{p['slug']}/index.html",
            "json": f"{SITE_URL}/api/questions/{p['slug']}.json",
        }
        for p in papers
    ]
    (api / "papers.json").write_text(
        json.dumps({"site": SITE_NAME, "papers": papers_meta}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    (api / "questions.json").write_text(
        json.dumps({"site": SITE_NAME, "questions": all_questions}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    q_api = api / "questions"
    q_api.mkdir(exist_ok=True)
    for paper in papers:
        (q_api / f"{paper['slug']}.json").write_text(
            json.dumps(paper, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    (api / "search-index.json").write_text(
        json.dumps(search_index, ensure_ascii=False), encoding="utf-8"
    )
    (api / "tags.json").write_text(
        json.dumps(
            {t: len(v) for t, v in sorted(tag_map.items(), key=lambda kv: -len(kv[1]))},
            ensure_ascii=False, indent=1,
        ),
        encoding="utf-8",
    )

    # ---------- 选题索引：全站每题一行，不含答案或解析正文 ----------
    def brief_stem(q: dict, width: int = 96) -> str:
        value = re.sub(r"\s+", " ", q.get("stem", "")).strip()
        return value[:width] + ("…" if len(value) > width else "")

    type_labels = {
        "choice": "选择题", "calc": "计算题", "calculation": "计算题",
        "analysis": "分析题", "design": "设计题", "simplification": "化简题",
    }
    index_rows: list[dict] = []
    for paper in papers:
        title = paper_title(paper)
        for q in paper["questions"]:
            answer_available = bool(q.get("answer"))
            explanation_available = bool(q.get("explanation") or q.get("answer_blocks"))
            index_rows.append({
                "id": q["id"],
                "url": q_url(q["id"]),
                "paper_url": f"{SITE_URL}/paper/{paper['slug']}/index.html#{q['id']}",
                "paper": title,
                "school": paper.get("school") or "未标注学校",
                "year": paper.get("year"),
                "subject": q.get("subject") or ("数电" if "第二部分" in (q.get("part") or "") else "模电"),
                "knowledge_points": q.get("tags", []),
                "type": type_labels.get(q.get("type"), q.get("section") or q.get("type") or "未标注"),
                "review_status": q.get("review_status") or "未校对",
                "answer_available": answer_available,
                "explanation_available": explanation_available,
                "has_figure": bool(q.get("figures") or q.get("source_images")),
                "stem_preview": brief_stem(q),
                "difficulty": q.get("difficulty"),
            })

    index_header = [
        f"{SITE_NAME} · 选题索引",
        f"版本：{INDEX_VERSION}",
        f"更新时间：{INDEX_UPDATED_AT}",
        f"覆盖：{len(papers)} 份试卷，{len(index_rows)} 道题",
        "说明：本索引不包含答案或解析正文；‘可用’只表示单题页已收录相应内容。",
        "校对状态仅有三种：未校对 / 题干已校对 / 解析已校对。",
        "",
        "题目ID\t绝对单题链接\t学校年份\t科目\t具体知识点\t题型\t校对状态\t答案\t解析\t题干要点",
    ]
    index_lines = index_header + [
        "\t".join([
            row["id"], row["url"], f'{row["school"]}{row["year"] or "年份未标注"}',
            row["subject"], "、".join(row["knowledge_points"]) or "未标注",
            row["type"], row["review_status"],
            "可用" if row["answer_available"] else "不可用",
            "可用" if row["explanation_available"] else "不可用",
            row["stem_preview"].replace("\t", " "),
        ])
        for row in index_rows
    ]
    index_text = "\n".join(index_lines) + "\n"
    (site_dir / "选题索引.txt").write_text(index_text, encoding="utf-8")
    (site_dir / "question-index.txt").write_text(index_text, encoding="utf-8")

    index_md = [
        f"# {SITE_NAME} · 选题索引", "",
        f"版本：{INDEX_VERSION}", "", f"更新时间：{INDEX_UPDATED_AT}", "",
        "本索引不包含答案或解析正文。", "",
    ]
    for row in index_rows:
        availability = (
            f'答案{"可用" if row["answer_available"] else "不可用"}、'
            f'解析{"可用" if row["explanation_available"] else "不可用"}'
        )
        index_md.append(
            f'- [{row["id"]}] {row["school"]}{row["year"] or ""} · {row["subject"]} · '
            f'{row["type"]} · {"、".join(row["knowledge_points"]) or "未标注"} · '
            f'{row["review_status"]} · {availability} → {row["url"]}'
        )
    md_text = "\n".join(index_md) + "\n"
    (site_dir / "question-index.md").write_text(md_text, encoding="utf-8")
    (site_dir / "question-index.html").write_text(
        render_layout("选题索引", md_to_html(md_text), 0), encoding="utf-8"
    )
    (api / "question-index.json").write_text(
        json.dumps({
            "site": SITE_NAME, "version": INDEX_VERSION, "updated_at": INDEX_UPDATED_AT,
            "count": len(index_rows), "questions": index_rows,
        }, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    llms = [f"# {SITE_NAME}", "", f"> {SITE_TAGLINE}。共 {len(papers)} 份试卷、{total_q} 道题，"
            f"其中 {total_a} 题带答案与解析。", "",
            "## 试卷清单", ""]
    for p in papers_meta:
        llms.append(
            f"- [{p['title']}]({p['url']}) · {p['questions']} 题 / 答案 {p['with_answer']} · "
            f"JSON: {p['json']}"
        )
    if browse_only:
        llms += ["", "## 只有原卷（扫描件，暂未切题）", ""]
        for p in browse_only:
            llms.append(
                f"- {p.get('school') or '未标注学校'} {p.get('code') or ''} "
                f"{p.get('year') or ''} · 原卷 {p.get('page_count', 0)} 页 · "
                f"{SITE_URL}/paper/{p['slug']}/index.html"
            )
    llms += ["", "## 机器可读接口", "",
             f"- 全部题目: {SITE_URL}/api/questions.json",
             f"- 试卷清单: {SITE_URL}/api/papers.json",
             f"- 知识点统计: {SITE_URL}/api/tags.json",
             f"- 全量纯文本: {SITE_URL}/llms-full.txt",
             f"- 接口定义: {SITE_URL}/openapi.yaml", "",
             "## 想让模型帮你挑题时先读这个", "",
             f"- 推荐上传/读取的纯文本选题索引（不含答案解析正文）：{SITE_URL}/选题索引.txt",
             f"- Markdown 版：{SITE_URL}/question-index.md",
             f"- 同上的 JSON 版本：{SITE_URL}/api/question-index.json", "",
             "  ⚠️ 有些抓取工具不认 text/markdown，读不了上面那个 .md；那就用这两份同内容的：",
             f"  · 纯文本：{SITE_URL}/question-index.txt （Content-Type: text/plain）",
             f"  · 网页版：{SITE_URL}/question-index.html （Content-Type: text/html）", "",
             "## 单题地址（AI 引用用这个）", "",
             f"- 每题一个稳定地址：{SITE_URL}/question/<question_id>.html",
             "  · 例：https://jsidiaowojd-hash.github.io/electronics-exam-bank/question/zsu-885-2024-p1-q11.html",
             "- ID 规则：`<试卷 slug>-q<阿拉伯数字题号>`；卷内分「部分」时插一段 `p<部分序号>`；",
             "  用「一、二、三」编号的大题标记为 `c<序号>`（例如 `zsu-885-2024-p1-c2` 是中大第一部分第 2 道大题）。",
             "- 单题页里含题干、配图、选项、答案解析和原卷裁图，可直接作为引用来源。", "",
             "## 使用说明", "",
             "题目 JSON 字段：id / number / part / section / subject / type / stem / options / figures / "
             "source_images / answer / explanation / tags / page / confidence / review_status。",
             "review_status 是独立人工校对状态：未校对、题干已校对、解析已校对。", ""]
    (site_dir / "llms.txt").write_text("\n".join(llms), encoding="utf-8")

    full = [f"# {SITE_NAME} 全量题目", ""]
    for paper in papers:
        full += [f"## {paper_title(paper)}", ""]
        for q in paper["questions"]:
            full.append(f"### 第 {q['number']} 题（{q.get('section') or ''}）")
            full.append(q["stem"])
            for opt in q.get("options", []):
                full.append(f"{opt['label']}. {opt['text']}")
            if q.get("figures"):
                full.append(f"[配图] {SITE_URL}/{q['figures'][0]}")
            full.append(f"答案：{q.get('answer') or '未收录'}")
            if q.get("explanation"):
                full.append(f"解析：{q['explanation']}")
            full.append(f"知识点：{'、'.join(q.get('tags', [])) or '未标注'}")
            full.append("")
    (site_dir / "llms-full.txt").write_text("\n".join(full), encoding="utf-8")

    urls = ["index.html", "search/index.html", "llms.txt", "llms-full.txt", "api/papers.json"]
    urls += [
        "question-index.md",
        "question-index.txt",
        "选题索引.txt",
        "question-index.html",
        "api/question-index.json",
    ]
    urls += [f"paper/{p['slug']}/index.html" for p in papers]
    urls += [f"paper/{p['slug']}/index.html" for p in browse_only]
    urls += [f"question/{q['id']}.html" for p in papers for q in p["questions"]]
    urls += [f"tag/{tag_slug(t)}/index.html" for t in tag_map]
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        sitemap.append(f"<url><loc>{SITE_URL}/{u}</loc></url>")
    sitemap.append("</urlset>")
    (site_dir / "sitemap.xml").write_text("\n".join(sitemap), encoding="utf-8")
    (site_dir / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n", encoding="utf-8"
    )
    (site_dir / "openapi.yaml").write_text(
        OPENAPI.replace("https://example.com", SITE_URL), encoding="utf-8"
    )

    return {"papers": len(papers), "questions": total_q, "tags": len(tag_map)}


OPENAPI = """openapi: 3.1.0
info:
  title: 数模电考研真题库 API
  version: "1.0"
  description: 供 ChatGPT Custom GPT Actions 查询历年数模电考研真题、答案与解析。
servers:
  - url: https://example.com
paths:
  /api/papers.json:
    get:
      operationId: listPapers
      summary: 列出全部试卷（学校、科目代码、年份、题量）
      responses:
        "200":
          description: 试卷列表
          content:
            application/json:
              schema:
                type: object
                properties:
                  papers:
                    type: array
                    items:
                      type: object
                      properties:
                        slug: {type: string}
                        school: {type: string}
                        code: {type: string}
                        year: {type: integer}
                        title: {type: string}
                        questions: {type: integer}
                        with_answer: {type: integer}
                        json: {type: string}
  /api/questions.json:
    get:
      operationId: listQuestions
      summary: 返回全部题目（含题干、选项、答案、解析、知识点）
      responses:
        "200":
          description: 题目列表
          content:
            application/json:
              schema:
                type: object
                properties:
                  questions:
                    type: array
                    items: {$ref: "#/components/schemas/Question"}
  /api/questions/{slug}.json:
    get:
      operationId: getPaper
      summary: 按试卷取题
      parameters:
        - name: slug
          in: path
          required: true
          schema: {type: string}
      responses:
        "200":
          description: 该试卷的全部题目
components:
  schemas:
    Question:
      type: object
      properties:
        id: {type: string}
        paper: {type: string}
        number: {type: integer}
        section: {type: string}
        type: {type: string}
        stem: {type: string}
        options:
          type: array
          items:
            type: object
            properties:
              label: {type: string}
              text: {type: string}
        answer: {type: string}
        explanation: {type: string}
        tags:
          type: array
          items: {type: string}
        figures:
          type: array
          items: {type: string}
        confidence: {type: string}
"""


def main() -> None:
    global SITE_URL
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--site", type=Path, default=Path("site"))
    ap.add_argument(
        "--site-url",
        default=os.environ.get("SITE_URL", SITE_URL),
        help="站点对外访问地址，写进 llms.txt / sitemap.xml / openapi.yaml",
    )
    args = ap.parse_args()
    SITE_URL = args.site_url.rstrip("/")
    if args.site.exists():
        for name in ("paper", "tag", "search", "api"):
            shutil.rmtree(args.site / name, ignore_errors=True)
    stats = build(args.data, args.site)
    print(f"[build] 试卷 {stats['papers']} 份 · 题目 {stats['questions']} 道 · 知识点 {stats['tags']} 个")
    print(f"[build] 站点输出 -> {args.site}")


if __name__ == "__main__":
    main()
