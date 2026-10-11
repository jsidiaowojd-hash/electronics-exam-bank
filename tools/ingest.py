#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数模电考研真题站点 —— 第一步：PDF 入库

把一份考研真题 PDF 拆成机器可读的中间产物：
  * 逐页文本（自动剔除水印字、页眉页脚、机构广告）
  * 逐题图形（优先抽取 PDF 内嵌的原始图片，干净无水印；抽不到时从页面渲染图裁切）
  * 整页渲染图（供"查看原文"对照）

用法：
    python tools/ingest.py --pdf-dir "C:/path/to/pdfs" --out data
    python tools/ingest.py --pdf "某校2024真题.pdf" --out data

输出：
    data/sources.json                 试卷清单（可手工改学校/科目/年份）
    data/papers/<slug>.json           每份试卷的逐页内容
    site/assets/figs/<slug>/*.png     题目图形
    site/assets/pages/<slug>/*.png    整页图
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import statistics
from pathlib import Path

import pdfplumber
from PIL import Image
from pypdf import PdfReader

try:  # 同目录导入
    from watermark import clean_pdf
except ImportError:  # 作为脚本直接运行时
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from watermark import clean_pdf
logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pdfplumber").setLevel(logging.ERROR)

# ---------------------------------------------------------------- 元数据识别

SCHOOL_ALIASES = [
    (("中山大学", "中大", "zsu"), "中山大学", "zsu"),
    (("华中科技大学", "华科", "hust"), "华中科技大学", "hust"),
    (("西安邮电大学", "西邮", "xiyou", "xupt"), "西安邮电大学", "xupt"),
    (("中国科学院大学", "中科院", "ucas", "cas"), "中国科学院大学", "ucas"),
    (("广东工业大学", "广工", "gdut"), "广东工业大学", "gdut"),
]

CODE_PATTERNS = [
    r"(?<!\d)(\d{3})(?!\d)\s*(?:电子技术|数模电|真题|模电|电子)",
    r"[-\s](\d{3})[-\s.]",
    r"(\d{3})\s*数模电",
]


def guess_meta(path: Path) -> dict:
    """从文件名猜学校 / 科目代码 / 年份，猜不到就留空等人工补。"""
    name = path.stem
    school, school_slug = "", ""
    for aliases, canonical, slug in SCHOOL_ALIASES:
        if any(a.lower() in name.lower() for a in aliases):
            school, school_slug = canonical, slug
            break

    code = ""
    for pat in CODE_PATTERNS:
        m = re.search(pat, name)
        if m:
            code = m.group(1)
            break
    if not code:
        m = re.search(r"(\d{3})", name)
        code = m.group(1) if m else ""

    year = None
    m = re.search(r"(20\d{2})", name)
    if m:
        year = int(m.group(1))
    else:
        m = re.search(r"(?<!\d)(\d{2})\s*年", name)
        if m and 10 <= int(m.group(1)) <= 30:
            year = 2000 + int(m.group(1))
        else:  # 形如 "24华科831..." 的前缀写法
            m = re.match(r"^\s*(\d{2})(?!\d)", name)
            if m and 10 <= int(m.group(1)) <= 30:
                year = 2000 + int(m.group(1))

    return {"school": school, "school_slug": school_slug, "code": code, "year": year}


def make_slug(meta: dict, path: Path) -> str:
    parts = []
    if meta["school_slug"]:
        parts.append(meta["school_slug"])
    if meta["code"]:
        parts.append(str(meta["code"]))
    if meta["year"]:
        parts.append(str(meta["year"]))
    if not parts:  # 文件名里什么线索都没有，退回到清洗后的文件名
        parts = [re.sub(r"[^a-z0-9]+", "", path.stem.lower())[:16] or "paper"]
    elif len(parts) == 1 and not meta["school_slug"]:
        parts.insert(0, "exam")
    return "-".join(parts)


def dedupe_key(name: str) -> str:
    """去掉「(1)」「-1」这类副本标记后的归一化名字，用于识别同一个卷子的多份拷贝。"""
    stem = Path(name).stem
    stem = re.sub(r"[\s]*[\(（\[【]\s*\d{1,3}\s*[\)）\]】]\s*$", "", stem)
    stem = re.sub(r"[\s]*[-_]\s*\d{1,2}\s*$", "", stem)
    return re.sub(r"[\s\-_（）()]+", "", stem).lower()


# ---------------------------------------------------------------- 文本清洗

# 机构广告、答疑群号等噪声（保留正文，只去掉括号里的推广语）
AD_PATTERNS = [
    r"[（(]\s*刺猬哥考研团队[^）)]*[）)]",
    r"[（(]\s*星星哥[^）)]*[）)]",
    r"[（(]\s*(?:小熊哥|小熊猫哥|小木哥|刺猬哥|星星哥)[^）)]*[）)]",
    r"[（(]\s*(?:华科|中大|西邮|广工|中科院)[^）)]{0,20}答疑群[^）)]*[）)]",
    r"刺猬哥考研团队，?答疑交流群\s*\d+",
    r"(?:小熊哥|小木哥)?QQ\s*[:：]?\s*\d{6,}",
    r"(?:小熊哥|小熊猫哥|小木哥|刺猬哥|星星哥)\s*(?:QQ|微信|群)\s*[:：]?\s*\d{0,12}",
    r"(?:华科|中大|西邮|广工|中科院|中大)\s*\d{0,4}\s*交流答疑群\s*[:：]?\s*\d{0,12}",
    r"答疑交流群\s*\d{6,}",
    r"微信\s*[:：]?\s*[A-Za-z0-9_\-]{4,}",
    r"QQ\s*群\s*[:：]?\s*\d{6,}",
]


def strip_ads(text: str) -> str:
    for pat in AD_PATTERNS:
        text = re.sub(pat, "", text)
    return text


def line_key(text: str) -> str:
    """归一化行文本，用于识别跨页重复的页眉页脚。"""
    return re.sub(r"[\s\d\-—_·．.、:：()（）\[\]]+", "", text)


def collect_repeated_lines(pages_lines: list[list[str]], doc_pages: int) -> set[str]:
    from collections import Counter

    counter = Counter()
    for lines in pages_lines:
        for key in {line_key(l) for l in lines if len(line_key(l)) >= 4}:
            counter[key] += 1
    threshold = max(3, int(doc_pages * 0.5))
    return {k for k, v in counter.items() if v >= threshold}


# ---------------------------------------------------------------- 图形处理

def render_page(page, resolution: int) -> Image.Image:
    return page.to_image(resolution=resolution).original.convert("RGB")


def native_figures(pdf_path: Path, page_index: int) -> list[tuple[Image.Image, str]]:
    """抽取 PDF 内嵌位图（通常就是干净的水印-free 电路图）。"""
    try:
        reader = PdfReader(str(pdf_path))
        page = reader.pages[page_index]
        out = []
        for img in page.images:
            try:
                pil = img.image
            except Exception:
                continue
            if pil is None:
                continue
            pil = pil.convert("RGB")
            out.append((pil, img.name))
        return out
    except Exception:
        return []


def match_native_index(figs: list[tuple[Image.Image, str]], bbox, used: set[int]):
    """按宽高比把 pdfplumber 的图形框对应到内嵌位图，返回下标。"""
    w = max(1e-6, bbox[2] - bbox[0])
    h = max(1e-6, bbox[3] - bbox[1])
    target = w / h
    best, best_score = None, 99.0
    for idx, (pil, _name) in enumerate(figs):
        if idx in used:
            continue
        ratio = pil.width / max(1, pil.height)
        score = abs(ratio - target) / target
        if score < best_score:
            best, best_score = idx, score
    return best if best_score < 0.20 else None


def _cluster_boxes(boxes: list[tuple[float, float, float, float]], gap: float = 8.0):
    """把零散的矢量线段/矩形按邻近关系聚成一块块图形区域。"""
    parent = list(range(len(boxes)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        a, b = find(i), find(j)
        if a != b:
            parent[b] = a

    def near(a, b):
        return not (
            a[2] + gap < b[0] or b[2] + gap < a[0] or a[3] + gap < b[1] or b[3] + gap < a[1]
        )

    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if near(boxes[i], boxes[j]):
                union(i, j)

    groups: dict[int, list] = {}
    for i, box in enumerate(boxes):
        groups.setdefault(find(i), []).append(box)

    merged = []
    for items in groups.values():
        merged.append(
            (
                min(b[0] for b in items),
                min(b[1] for b in items),
                max(b[2] for b in items),
                max(b[3] for b in items),
                len(items),
            )
        )
    return merged


def figure_regions(page, raster_min: tuple[float, float] = (40, 30)):
    """返回页面上所有候选图形区域：位图框 + 矢量图形簇。"""
    width, height = float(page.width), float(page.height)
    regions = []

    for im in page.images:
        x0, top, x1, bottom = im["x0"], im["top"], im["x1"], im["bottom"]
        w, h = x1 - x0, bottom - top
        if w < raster_min[0] or h < raster_min[1] or w * h < 4000:
            continue
        if w > width * 0.96 and h > height * 0.9:  # 整页底图/水印层
            continue
        regions.append({"kind": "raster", "bbox": (x0, top, x1, bottom), "weight": 0})

    vector_boxes = []
    for coll in (page.lines, page.rects, page.curves):
        for obj in coll:
            x0, top, x1, bottom = obj["x0"], obj["top"], obj["x1"], obj["bottom"]
            if (x1 - x0) > width * 0.9 and (bottom - top) < 3:  # 长横线：分栏/页眉线
                continue
            vector_boxes.append((x0, top, x1, bottom))

    for x0, top, x1, bottom, count in _cluster_boxes(vector_boxes):
        w, h = x1 - x0, bottom - top
        if w < 60 or h < 40 or count < 4:
            continue
        if w > width * 0.94 and h > height * 0.8:
            continue
        regions.append({"kind": "vector", "bbox": (x0, top, x1, bottom), "weight": count})

    # 位图区域优先，矢量簇若与位图重叠度很高则丢弃
    def iou(a, b):
        ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
        iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
        inter = ix * iy
        if inter <= 0:
            return 0.0
        area_a = (a[2] - a[0]) * (a[3] - a[1])
        area_b = (b[2] - b[0]) * (b[3] - b[1])
        return inter / max(1e-6, min(area_a, area_b))

    rasters = [r for r in regions if r["kind"] == "raster"]
    keep = list(rasters)
    for r in regions:
        if r["kind"] == "raster":
            continue
        if any(iou(r["bbox"], s["bbox"]) > 0.7 for s in rasters):
            continue
        keep.append(r)

    keep.sort(key=lambda r: (round(r["bbox"][1]), r["bbox"][0]))
    return keep


# ---------------------------------------------------------------- 主流程

def ingest_pdf(path: Path, out_root: Path, site_root: Path, do_clean: bool = True) -> dict:
    meta = guess_meta(path)
    slug = make_slug(meta, path)
    source_pdf = path
    clean_note = ""
    if do_clean:
        clean_path = out_root.parent / "work" / "clean" / f"{slug}.pdf"
        if not clean_path.exists():
            try:
                stats = clean_pdf(path, clean_path)
                clean_note = (
                    f"去除水印字块 {stats['blocks_removed'] + stats['xobject_blocks_removed']} 处"
                )
            except Exception as exc:
                print(f"    [warn] 去水印失败，改用原文件：{type(exc).__name__} {exc}")
        if clean_path.exists():
            path = clean_path

    fig_dir = site_root / "assets" / "figs" / slug
    page_dir = site_root / "assets" / "pages" / slug
    fig_dir.mkdir(parents=True, exist_ok=True)
    page_dir.mkdir(parents=True, exist_ok=True)

    with pdfplumber.open(path) as pdf:
        # 正文尺寸的中位数：远大于它的字基本就是水印/大标题
        sizes = []
        for pg in pdf.pages[: min(10, len(pdf.pages))]:
            sizes += [c["size"] for c in pg.chars]
        median_size = statistics.median(sizes) if sizes else 12.0
        wm_threshold = max(28.0, median_size * 2.4)

        page_records = []
        raw_lines_per_page = []
        for i, page in enumerate(pdf.pages):
            kept = page.filter(
                lambda o: not (o["object_type"] == "char" and o["size"] > wm_threshold)
            )
            lines = kept.extract_text_lines() or []
            raw_lines_per_page.append([l["text"] for l in lines])
            page_records.append(
                {
                    "n": i + 1,
                    "page": page,
                    "lines": lines,
                    "images": list(page.images),
                    "width": float(page.width),
                    "height": float(page.height),
                }
            )

        repeated = collect_repeated_lines(raw_lines_per_page, len(pdf.pages))

        pages_out = []
        scan_pages = 0
        for rec in page_records:
            rec["regions"] = figure_regions(rec["page"])
            if any(
                (im["x1"] - im["x0"]) > rec["width"] * 0.8
                and (im["bottom"] - im["top"]) > rec["height"] * 0.75
                for im in rec["images"]
            ):
                scan_pages += 1
            kept_lines = []
            for line in rec["lines"]:
                text = strip_ads(line["text"]).strip()
                if not text:
                    continue
                key = line_key(text)
                if key and key in repeated:
                    continue
                if re.fullmatch(r"[-—\s]*\d{1,3}[-—\s]*", text):  # 纯页码
                    continue
                kept_lines.append(
                    {
                        "text": text,
                        "top": round(float(line["top"]), 1),
                        "bottom": round(float(line["bottom"]), 1),
                    }
                )

            rendered = None
            figures = []
            native = native_figures(path, rec["n"] - 1)
            used = set()
            for k, region in enumerate(rec["regions"]):
                bbox = region["bbox"]
                name = f"p{rec['n']:02d}-{k + 1}.png"
                pil = None
                if region["kind"] == "raster":
                    idx = match_native_index(native, bbox, used)
                    if idx is not None and native[idx][0].width >= 260:
                        used.add(idx)
                        pil = native[idx][0]
                if pil is None:
                    # 矢量图或位图不可用：从 300dpi 页面渲染图裁切
                    if rendered is None:
                        with pdfplumber.open(path) as p2:
                            rendered = render_page(p2.pages[rec["n"] - 1], 300)
                    scale = rendered.width / rec["width"]
                    pil = rendered.crop(
                        (
                            int(max(0.0, bbox[0] - 3) * scale),
                            int(max(0.0, bbox[1] - 3) * scale),
                            int(min(rec["width"], bbox[2] + 3) * scale),
                            int(min(rec["height"], bbox[3] + 3) * scale),
                        )
                    )
                if pil.width < 120 or pil.height < 60:
                    continue
                pil.save(fig_dir / name)
                figures.append(
                    {
                        "file": f"assets/figs/{slug}/{name}",
                        "kind": region["kind"],
                        "top": round(float(bbox[1]), 1),
                        "bottom": round(float(bbox[3]), 1),
                        "width": pil.width,
                        "height": pil.height,
                    }
                )

            page_png = f"assets/pages/{slug}/p{rec['n']:02d}.png"
            if not (site_root / page_png).exists():
                with pdfplumber.open(path) as p2:
                    render_page(p2.pages[rec["n"] - 1], 150).save(site_root / page_png)

            pages_out.append(
                {
                    "n": rec["n"],
                    "image": page_png,
                    "width": rec["width"],
                    "height": rec["height"],
                    "figures": figures,
                    "lines": kept_lines,
                    "text": "\n".join(l["text"] for l in kept_lines),
                }
            )

    return {
        "slug": slug,
        "source_pdf": source_pdf.name,
        "clean_note": clean_note,
        "school": meta["school"],
        "school_slug": meta["school_slug"],
        "code": meta["code"],
        "year": meta["year"],
        "scan_style": scan_pages >= max(1, int(len(page_records) * 0.7)),
        "pages": pages_out,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", type=Path)
    ap.add_argument(
        "--pdf-root",
        type=Path,
        action="append",
        help="递归扫描该目录下所有 PDF（可重复指定），CI 里用它把仓库里的卷子一网打尽",
    )
    ap.add_argument("--pdf", type=Path, action="append")
    ap.add_argument("--out", type=Path, default=Path("data"))
    ap.add_argument("--site", type=Path, default=Path("site"))
    ap.add_argument("--no-clean", action="store_true", help="跳过去水印步骤")
    args = ap.parse_args()

    targets: list[Path] = []
    if args.pdf_dir:
        targets += sorted(p for p in args.pdf_dir.glob("*.pdf"))
    for root in args.pdf_root or []:
        for p in sorted(root.rglob("*.pdf")):
            # 跳过构建产物与依赖目录，避免把生成出来的 PDF 又扫一遍
            if any(part in {"build", "site", ".git", "node_modules", "public"} for part in p.parts):
                continue
            targets.append(p)
    if args.pdf:
        targets += args.pdf

    # 同一份卷子的多份拷贝（例如 xxx(1).pdf）只留一份
    seen_names: set[str] = set()
    deduped: list[Path] = []
    for t in sorted(targets, key=lambda p: len(p.name)):  # 优先保留名字干净的那份
        key = dedupe_key(t.name)
        if key in seen_names:
            print(f"[dup ] 跳过重复文件 {t.name}")
            continue
        seen_names.add(key)
        deduped.append(t)
    targets = sorted(deduped)

    # 教材等超大的 PDF 不入库
    targets = [t for t in targets if t.stat().st_size < 20_000_000]

    papers_dir = args.out / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)

    sources = []
    for pdf in targets:
        try:
            rec = ingest_pdf(pdf, args.out, args.site, do_clean=not args.no_clean)
        except Exception as exc:  # 单份失败不影响整体
            print(f"[skip] {pdf.name}: {type(exc).__name__} {exc}")
            continue
        (papers_dir / f"{rec['slug']}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        n_fig = sum(len(p["figures"]) for p in rec["pages"])
        print(
            f"[ok] {rec['slug']:22s} pages={len(rec['pages']):3d} figures={n_fig:3d} "
            f"school={rec['school'] or '?'} year={rec['year'] or '?'}"
        )
        sources.append(
            {
                "slug": rec["slug"],
                "file": pdf.name,
                "school": rec["school"],
                "school_slug": rec["school_slug"],
                "code": rec["code"],
                "year": rec["year"],
                "pages": len(rec["pages"]),
                "figures": n_fig,
            }
        )

    (args.out / "sources.json").write_text(
        json.dumps(sources, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"\n共入库 {len(sources)} 份试卷 -> {args.out/'papers'}")


if __name__ == "__main__":
    main()
