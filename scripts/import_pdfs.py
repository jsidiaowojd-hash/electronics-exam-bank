#!/usr/bin/env python3
"""Render PDF exam archive; deduplicate identical bytes, keep variants, group by subject."""
from __future__ import annotations
import hashlib
import html
import json
import re
import shutil
import unicodedata
from collections import defaultdict
from pathlib import Path
import fitz

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site"

def esc(s):
    return html.escape(str(s), quote=True)

def norm_name(s):
    return re.sub(r"(?:\.pdf)+$", "", s, flags=re.I).strip()

def uid(name, digest):
    base = unicodedata.normalize("NFKD", name).lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:40]
    return f"{base or 'pdf'}-{digest[:12]}"

def category(name):
    s = name.lower()
    if "中大" in s or "中山" in s:
        return "中山大学 · 885" if "885" in s else "中山大学 · 待确认科目"
    if "华科" in s or "hust" in s:
        return "华中科技大学 · 831" if "831" in s else "华中科技大学 · 待确认科目"
    if "中科院" in s or "国科大" in s:
        return "中科院 · 856" if "856" in s else "中科院 · 待确认科目"
    if "西安邮电" in s or "西邮" in s:
        return "西安邮电大学 · 823" if "823" in s else "西安邮电大学 · 待确认科目"
    if "广工" in s or "广东工业" in s:
        return "广东工业大学 · 849" if "849" in s else "广东工业大学 · 待确认科目"
    if re.search(r"885", s):
        return "885 回忆资料 · 原件未注明院校"
    if re.search(r"\b8(?:60|61|62|63|65|07|08|12|13)\b", s) or re.search(r"(860|861|862|863|865|907|908|912|913)", s):
        return "其他院校 · 电子技术（待核验）"
    return "其他资料 · 待分类"

def year_of(name):
    match = re.search(r"(?:20)?(0[5-9]|1[0-9]|2[0-9])\s*(?:年|届|华科|中大|中科院|西安|范围|[ _-])", name)
    if match:
        year = int(match.group(1))
        return (2000 + year, True)
    match = re.search(r"(20[0-3][0-9])", name)
    return (int(match.group(1)), True) if match else (0, False)

def meta_for(pdf):
    # Optional JSON can override category, year, title, number of original question pages.
    path = pdf.with_suffix(".json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}

def digest_file(pdf):
    h = hashlib.sha256()
    with pdf.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def copy_site():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    for n in ("index.html", "2021-hust-831.html", "original-practice.html", "labels.html"):
        if (ROOT / n).exists():
            shutil.copy2(ROOT / n, OUT / n)
    for n in ("assets", "questions", "data"):
        if (ROOT / n).exists():
            shutil.copytree(ROOT / n, OUT / n, dirs_exist_ok=True)
    (OUT / "exams").mkdir(exist_ok=True)
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

CSS = """
*{box-sizing:border-box}body{font:16px/1.75 -apple-system,BlinkMacSystemFont,"Microsoft Yahei",sans-serif;background:#f5f7fb;color:#20324a;margin:0}
a{color:#1e5dbc;text-decoration:none}a:hover{text-decoration:underline}
.container{max-width:1050px;margin:32px auto;padding:0 18px}.top{background:white;border:1px solid #dce4ee;border-radius:14px;padding:25px;margin-bottom:19px}
h1{line-height:1.35;margin:0 0 10px;font-size:30px}h2{font-size:22px;margin-top:32px}
.muted{font-size:14px;color:#687b91}.note{background:#fff6dc;border-left:4px solid #d99c19;padding:12px 17px;border-radius:5px}
.row{background:white;padding:14px 20px;border:1px solid #e0e7f0;border-radius:10px;margin:11px 0}
.row .name{font-weight:700;overflow-wrap:anywhere}.meta{display:flex;gap:8px;flex-wrap:wrap;margin-top:7px;font-size:12px;color:#60728b}
.chip{padding:2px 7px;border-radius:5px;background:#ecf2fb}.search{width:100%;font:inherit;padding:12px;border:1px solid #c7d5e8;border-radius:8px}
.sheet{margin:17px 0;background:white;padding:14px;border:1px solid #dce4ee;border-radius:10px}
.sheet img{width:100%;height:auto;display:block}.sheet figcaption{font-weight:600;font-size:14px;color:#50657e;margin-bottom:8px}
details{background:white;margin:14px 0;border:1px solid #dce4ee;border-radius:10px;padding:12px}summary{cursor:pointer;font-weight:700;color:#1b55a5}
@media(max-width:650px){h1{font-size:24px}.top{padding:17px}.container{margin:10px auto}}

/* Sticky two-column reader */
.layout{max-width:1390px;margin:24px auto;padding:0 16px;display:grid;grid-template-columns:248px minmax(0,1fr);gap:22px;align-items:start}
.nav{position:sticky;top:16px;align-self:start;max-height:calc(100vh - 32px);overflow-y:auto;background:white;border:1px solid #dce4ee;border-radius:12px;padding:15px 12px;scrollbar-width:thin}
.nav .brand{font-weight:800;color:#274d7c;display:block;padding:3px 9px 12px;border-bottom:1px solid #e5eaf2}
.nav summary{font-size:14px;color:#365879;cursor:pointer;font-weight:700;padding:8px;list-style:auto}
.nav details{padding:0;margin:6px 0;border:none;background:transparent}
.nav a{display:block;padding:7px 10px;color:#4e6581;font-size:13px;border-radius:6px;overflow-wrap:anywhere;line-height:1.5}
.nav a:hover,.nav a:focus{background:#eaf2ff;text-decoration:none;color:#1c54aa}
.nav .short{font-size:12px;color:#65768c;padding:0 9px}
.reading{min-width:0;max-width:1000px}.reading>.top{margin-top:0}
.jump{scroll-margin-top:18px}.nav-toggle{display:none}
.group>h2{scroll-margin-top:20px}
@media(max-width:850px){.layout{display:block;padding:10px}.nav{position:static;max-height:360px;margin-bottom:15px}.nav-toggle{display:block;background:#eaf2ff;border:1px solid #cbdcf7;border-radius:8px;padding:8px 12px;cursor:pointer;font-weight:700;width:100%;text-align:left}.nav[data-collapsed="1"] .nav-content{display:none}.reading{max-width:none}.nav a{display:inline-block;margin-right:8px}}
"""
def header(title):
    return f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}｜电子技术真题</title><style>{CSS}</style></head><body><div class="container">'

def render(pdf, item):
    target = OUT / "exams" / item["slug"]
    target.mkdir(parents=True)
    parts = []
    nav_pages = []
    with fitz.open(pdf) as doc:
        total = len(doc)
        if total < 1:
            raise ValueError(f"Blank PDF: {pdf}")
        split = item.get("question_pages")
        if split is not None and not 0 <= int(split) <= total:
            raise ValueError(f"Invalid question_pages: {pdf}")
        for pno, page in enumerate(doc, 1):
            # JPEG reduces GitHub Pages artifact size for a large archive.
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), colorspace=fitz.csRGB, alpha=False)
            image = f"page-{pno:03}.jpg"
            pix.save(str(target / image), jpg_quality=80)
            if item["legacy"]:
                # The existing 2021 year-by-year page expects PNG assets.
                png_name = f"source-page-{pno}.png" if pno <= 6 else f"answer-page-{pno}.png"
                original = page.get_pixmap(matrix=fitz.Matrix(1.7, 1.7), alpha=False)
                original.save(str(OUT / "assets" / png_name))
            label = ("原题" if split is not None and pno <= int(split) else
                     "参考解析" if split is not None else "原卷页面")
            block = f'<figure class="sheet"><figcaption>第 {pno} 页 · {label}</figcaption><a href="{image}" target="_blank" rel="noopener"><img loading="lazy" src="{image}" alt="{esc(item["title"])} 第{pno}页"></a></figure>'
            anchor = f"page-{pno}"
            block = block.replace('<figure class="sheet">', f'<figure class="sheet jump" id="{anchor}">', 1)
            if label == "参考解析":
                block = f'<details class="jump" id="{anchor}"><summary>第 {pno} 页 · 展开参考解析</summary>{block}</details>'
                block = block.replace(f'<figure class="sheet jump" id="{anchor}">', '<figure class="sheet">', 1)
            nav_pages.append(f'<a href="#{anchor}">第 {pno:02d} 页 · {label}</a>')
            parts.append(block)
    item["pages"] = total
    nav = ('<aside class="nav" data-collapsed="0"><button class="nav-toggle" type="button" '
           'onclick="this.parentNode.dataset.collapsed=this.parentNode.dataset.collapsed===&#39;1&#39;?&#39;0&#39;:&#39;1&#39;">☰ 展开／收起页码导航</button>'
           '<div class="nav-content"><a class="brand" href="../index.html">← 全部真题</a>'
           '<div class="short">当前试卷 · 点击页码定位</div>' + ''.join(nav_pages) + '</div></aside>')
    content = (f'<div class="top"><h1>{esc(item["title"])}</h1>'
        f'<p class="muted">{esc(item["category"])} · {total} 页</p>'
        '<p class="note">右侧是原卷图片；左侧固定页码导航。参考解析按页折叠；图片可以放大。未确认分界的PDF不擅自区分答案。</p></div>'
        + ''.join(parts))
    (target / "index.html").write_text(header(item["title"])+
        '<div class="layout">'+nav+'<main class="reading">'+content+'</main></div></div></body></html>', encoding="utf-8")

def main():
    copy_site()
    pdfs = sorted([*ROOT.glob("*.pdf"), *(ROOT / "imports").glob("*.pdf")], key=lambda p: str(p).lower())
    seen = {}
    items = []
    dupes = []
    for pdf in pdfs:
        digest = digest_file(pdf)
        if digest in seen:
            dupes.append((str(pdf.relative_to(ROOT)), seen[digest]))
            continue
        seen[digest] = str(pdf.relative_to(ROOT))
        metadata = meta_for(pdf)
        title = str(metadata.get("title") or norm_name(pdf.name))
        cat = str(metadata.get("category") or category(title))
        year, confident = year_of(title)
        year = int(metadata.get("year") or year)
        special = norm_name(pdf.name).lower() == "2021-hust-831"
        slug = "2021-hust-831" if special else uid(title, digest)
        item = {"file": str(pdf.relative_to(ROOT)), "title":title,
                "category":cat, "year":year, "slug":slug,
                "question_pages": metadata.get("question_pages", 6 if special else None),
                "legacy":special,"sha256":digest}
        items.append((pdf,item))
    # Sort and group automatically; do not merge merely similar names.
    items.sort(key=lambda pair:(pair[1]["category"],-pair[1]["year"],pair[1]["title"]))
    for pdf,item in items:
        render(pdf,item)
        print(f'RENDER {item["category"]}: {item["title"]} ({item["pages"]} pages)')
    groups = defaultdict(list)
    for _,it in items:
        groups[it["category"]].append(it)
    priority = {"中山大学 · 885":0,"华中科技大学 · 831":1,"中科院 · 856":2,"西安邮电大学 · 823":3,"广东工业大学 · 849":4}
    chunks = []
    side_links = []
    for idx,cat in enumerate(sorted(groups,key=lambda k:(priority.get(k,9),k))):
        section_id = f"category-{idx}"
        side_links.append(f'<a href="#{section_id}">{esc(cat)}（{len(groups[cat])}）</a>')
        rows=[]
        for item in groups[cat]:
            when=f'{item["year"]} 年' if item["year"] else "年份待核对"
            rows.append(f'<article class="row" data-search="{esc(item["title"]+" "+cat+" "+when).lower()}"><div class="name"><a href="{esc(item["slug"])}/index.html">{esc(item["title"])}</a></div><div class="meta"><span class="chip">{when}</span><span class="chip">{item["pages"]} 页</span><span class="chip">PDF 原始图</span></div></article>')
        chunks.append(f'<section class="group" id="{section_id}"><h2>{esc(cat)} <small class="muted">（{len(rows)} 份）</small></h2>{"".join(rows)}</section>')
    notes=f'共收录 {len(items)} 份不同内容的 PDF，自动去重 {len(dupes)} 份相同内容的重复上传。名称相似但文件内容不同的版本均予以保留。'
    search='<input class="search" id="q" placeholder="搜索学校、年份、考试科目或文件名" oninput="let s=this.value.toLowerCase().trim();document.querySelectorAll(\'.row\').forEach(x=>x.style.display=x.dataset.search.includes(s)?\'\':\'none\');document.querySelectorAll(\'.group\').forEach(x=>x.style.display=[...x.querySelectorAll(\'.row\')].some(y=>y.style.display!==\'none\')?\'\':\'none\')">'
    side = ('<aside class="nav" data-collapsed="0"><button class="nav-toggle" type="button" '
            'onclick="this.parentNode.dataset.collapsed=this.parentNode.dataset.collapsed===&#39;1&#39;?&#39;0&#39;:&#39;1&#39;">☰ 展开／收起学校导航</button>'
            '<div class="nav-content"><a class="brand" href="../index.html">📘 电子技术题库</a>'
            '<div class="short">按院校／专业课浏览</div>' + ''.join(side_links) + '</div></aside>')
    page=(header("电子技术真题分类目录")+'<div class="layout">'+side+
          '<main class="reading"><div class="top"><h1>电子技术真题 · 分类目录</h1><p class="muted">'+esc(notes)+
          '</p>'+search+'</div>'+''.join(chunks)+'</main></div></div></body></html>')
    (OUT/"exams"/"index.html").write_text(page,encoding="utf-8")
    (OUT/"exams"/"manifest.json").write_text(json.dumps({
        "total":len(items),"duplicates": [{"file":a,"same_as":b} for a,b in dupes],
        "items":[it for _,it in items]
    },ensure_ascii=False,indent=2),encoding="utf-8")
    print(f'OK: {len(items)} unique, {len(dupes)} duplicate, {len(groups)} categories')

if __name__ == "__main__":
    main()

