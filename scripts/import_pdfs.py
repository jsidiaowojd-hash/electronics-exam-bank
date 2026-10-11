#!/usr/bin/env python3
"""Build GitHub Pages from a public exam index and PDF files in imports/."""
from __future__ import annotations
import html
import json
import re
import shutil
from pathlib import Path
import fitz

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site"
INBOX = ROOT / "imports"

def esc(value):
    return html.escape(str(value), quote=True)

def slugify(name):
    slug = re.sub(r"[^a-z0-9_-]+", "-", name.lower()).strip("-")
    return slug or "exam"

def copy_static():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    for file in ("index.html", "2021-hust-831.html", "original-practice.html"):
        src = ROOT / file
        if src.exists():
            shutil.copy2(src, OUT / file)
    for directory in ("questions", "assets"):
        src = ROOT / directory
        if src.exists():
            shutil.copytree(src, OUT / directory, dirs_exist_ok=True)

def render_pdf(pdf, title, question_pages, folder, legacy=False):
    folder.mkdir(parents=True, exist_ok=True)
    cards = []
    with fitz.open(pdf) as doc:
        total = len(doc)
        if total == 0:
            raise ValueError(f"empty PDF: {pdf.name}")
        if question_pages is not None:
            question_pages = int(question_pages)
            if not 0 <= question_pages <= total:
                raise ValueError(f"question_pages must be between 0 and {total}: {pdf.name}")
        for idx, page in enumerate(doc, 1):
            pix = page.get_pixmap(matrix=fitz.Matrix(1.7, 1.7), alpha=False)
            image_name = f"page-{idx:03d}.png"
            pix.save(str(folder / image_name))
            label = ("原题" if question_pages is not None and idx <= question_pages
                     else "答案与解析" if question_pages is not None
                     else "PDF 页面")
            cards.append((idx, image_name, label))
            if legacy:
                old_name = f"source-page-{idx}.png" if idx <= 6 else f"answer-page-{idx}.png"
                shutil.copy2(folder / image_name, OUT / "assets" / old_name)
    sections = []
    for idx, image_name, label in cards:
        block = (f'<section class="page"><h2>第 {idx} 页 · {esc(label)}</h2>'
                 f'<a href="{esc(image_name)}" target="_blank" rel="noopener">'
                 f'<img loading="lazy" src="{esc(image_name)}" alt="{esc(title)} 第 {idx} 页"></a></section>')
        if label == "答案与解析":
            block = f"<details><summary>展开第 {idx} 页答案与解析</summary>{block}</details>"
        sections.append(block)
    doc_html = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} · 电子技术真题</title>
<style>body{{background:#f6f8fc;color:#20334c;max-width:920px;margin:26px auto;padding:0 14px;font:16px/1.8 system-ui,"Microsoft Yahei",sans-serif}}
a{{color:#2563eb}}.page{{background:white;padding:15px;margin:20px 0;border:1px solid #dce5ef;border-radius:10px}}
img{{width:100%;height:auto;display:block}}details{{background:#fff;border:1px solid #dce5ef;border-radius:10px;margin:18px 0;padding:12px}}
summary{{cursor:pointer;color:#245ab8;font-weight:bold}}.notice{{background:#fff6db;padding:12px;border-left:4px solid #dca219}}</style></head>
<body><a href="../index.html">← 返回 PDF 题库目录</a>
<h1>{esc(title)}</h1><p>共 {total} 页，保留 PDF 题面、原始电路图与解析图片。点击图片可放大。</p>
<p class="notice">按页呈现的原始资料；每道大题的精确裁切、逐题答案对应、公式文本化仍需人工复核。非官方标准答案。</p>
{''.join(sections)}
</body></html>'''
    (folder / "index.html").write_text(doc_html, encoding="utf-8")
    return total

def main():
    copy_static()
    index_entries = []
    if INBOX.exists():
        pdfs = sorted([*INBOX.glob("*.pdf"), *ROOT.glob("*.pdf")], key=lambda p: p.name.lower())
        seen = set()
        for pdf in pdfs:
            normalized_stem = re.sub(r"(?:\.pdf)+$", "", pdf.name, flags=re.IGNORECASE)
            stem = slugify(normalized_stem)
            if stem in seen:
                raise ValueError(f"duplicate URL slug for: {pdf.name}")
            seen.add(stem)
            meta_file = pdf.with_suffix(".json")
            meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
            title = meta.get("title") or pdf.stem
            special = stem == "2021-hust-831"
            qp = meta.get("question_pages", 6 if special else None)
            total = render_pdf(pdf, title, qp, OUT / "exams" / stem, legacy=special)
            index_entries.append((stem, title, total))
    entries_html = "".join(
        f'<li><a href="{esc(s)}/index.html">{esc(title)}</a>（{count} 页）</li>'
        for s, title, count in index_entries
    ) or "<li>暂时还没有上传 PDF。请在 GitHub 的 imports/ 文件夹中添加 PDF。</li>"
    catalog = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>自动导入的 PDF 真题</title>
<style>body{{font:16px/1.9 system-ui,"Microsoft Yahei",sans-serif;max-width:860px;margin:35px auto;padding:20px;color:#20334c}}
a{{color:#2563eb}}li{{margin:12px 0}}</style></head><body>
<a href="../index.html">← 返回首页</a><h1>自动导入的 PDF 真题</h1>
<p>PDF 上传后由 GitHub Actions 统一转换和发布。本页面按文件名列出文档。</p>
<ul>{entries_html}</ul></body></html>'''
    (OUT / "exams").mkdir(exist_ok=True)
    (OUT / "exams" / "index.html").write_text(catalog, encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Built Pages site: {len(index_entries)} PDF(s), output {OUT}")

if __name__ == "__main__":
    main()
