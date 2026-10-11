#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
去水印：把 PDF 里的水印文字对象从内容流中整块摘除，正文与图形保持原样。

思路：
  1. 用 pdfplumber 定位"疑似水印字"——字号远大于正文的，或命中广告/群号文案的；
  2. 用 pypdf 取出页面内容流，逐个 BT..ET 文本块计算它的实际字号与落笔坐标；
  3. 命中水印的字块整块删除，重新写回内容流。

删除的是文本绘制指令，矢量电路图和正文文字不受影响。
"""

from __future__ import annotations

import argparse
import logging
import re
import statistics
from pathlib import Path

import pdfplumber
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject

logging.getLogger("pdfminer").setLevel(logging.ERROR)

# 命中这些文案的字，一律当作水印/广告
AD_TEXT = re.compile(
    r"(小熊猫哥|刺猬哥|星星哥|微电子考研|微电考研|考研微电|电子考研|"
    r"答疑群|交流群|答疑交流|QQ|qq群|微信|公众号|淘宝|bilibili|B站|"
    r"\d{6,})"
)

BT_BLOCK = re.compile(r"BT\b(.*?)\bET", re.S)
TF_RE = re.compile(r"/([A-Za-z0-9_.+-]+)\s+([\d.eE+-]+)\s+Tf")
TM_RE = re.compile(
    r"([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)\s+"
    r"([\d.eE+-]+)\s+([\d.eE+-]+)\s+Tm"
)


def watermark_boxes(page, size_cap: float):
    """超标大字的按字号整块删；小字广告则按位置精确删。"""
    boxes = []
    for ch in page.chars:
        if ch["size"] > size_cap:
            continue  # 交给字号规则处理，避免它的大包围盒误伤正文
        if AD_TEXT.search(ch["text"]):
            boxes.append((ch["x0"], ch["top"], ch["x1"], ch["bottom"]))
    return boxes


def filter_stream(data: bytes, boxes, page_height: float, size_cap: float):
    text = data.decode("latin-1")
    parts, cursor, removed = [], 0, 0
    for m in BT_BLOCK.finditer(text):
        body = m.group(1)
        tf = TF_RE.search(body)
        tm = TM_RE.findall(body)
        size_eff, origin = None, None
        if tf:
            fs = float(tf.group(2))
            scale = 1.0
            if tm:
                a, b, c, d = (float(x) for x in tm[0][:4])
                scale = abs(a * d - b * c) ** 0.5
            size_eff = fs * scale
        if tm:
            origin = (float(tm[0][4]), float(tm[0][5]))

        drop = bool(size_eff and size_eff > size_cap)
        if not drop and origin:
            x, y_top = origin[0], page_height - origin[1]
            for x0, t0, x1, b0 in boxes:
                if x0 - 2 <= x <= x1 + 2 and t0 - 3 <= y_top <= b0 + 6:
                    drop = True
                    break
        if drop:
            removed += 1
            parts.append(text[cursor : m.start()])
            cursor = m.end()
    parts.append(text[cursor:])
    return "".join(parts).encode("latin-1"), removed


def replace_stream(obj, new_data: bytes):
    """用新的解码后数据替换一个流对象（自动丢弃原压缩参数）。"""
    from pypdf.generic import NameObject

    fresh = DecodedStreamObject()
    for key, value in obj.items():
        if key in ("/Filter", "/DecodeParms", "/Length"):
            continue
        fresh[NameObject(key)] = value
    fresh.set_data(new_data)
    return fresh


def clean_xobjects(resources, size_cap: float, depth: int = 0) -> int:
    """递归清理 Form XObject 里的大字水印（按字号判断，不依赖坐标）。"""
    from pypdf.generic import NameObject

    if depth > 2 or resources is None:
        return 0
    xobjects = resources.get("/XObject")
    if not xobjects:
        return 0
    removed_total = 0
    for name in list(xobjects.keys()):
        try:
            obj = xobjects[name]
            if obj.get("/Subtype") != "/Form":
                continue
            data = obj.get_data()
            new_data, removed = filter_stream(data, [], 0.0, size_cap)
            if removed:
                xobjects[NameObject(name)] = replace_stream(obj, new_data)
                removed_total += removed
            sub = obj.get("/Resources")
            if sub:
                removed_total += clean_xobjects(sub, size_cap, depth + 1)
        except Exception:
            continue
    return removed_total


def clean_pdf(src: Path, dst: Path, size_factor: float = 2.0, size_cap: float = 22.0) -> dict:
    """生成去水印副本，返回统计信息。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    stats = {"pages": 0, "blocks_removed": 0, "xobject_blocks_removed": 0}

    with pdfplumber.open(src) as pdf:
        page_boxes = []
        for page in pdf.pages:
            sizes = [c["size"] for c in page.chars]
            med = statistics.median(sizes) if sizes else 12.0
            page_boxes.append(
                (watermark_boxes(page, max(size_cap, med * size_factor)), float(page.height))
            )

    reader = PdfReader(str(src))
    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        if i < len(page_boxes) and page_boxes[i][0]:
            boxes, height = page_boxes[i]
            try:
                data = page.get_contents().get_data()
                new_data, removed = filter_stream(data, boxes, height, size_cap)
                if removed:
                    stream = DecodedStreamObject()
                    stream.set_data(new_data)
                    page.replace_contents(stream)
                    stats["blocks_removed"] += removed
            except Exception as exc:  # 内容流结构异常时保留原样
                print(f"    [warn] page {i + 1} 清洗失败：{type(exc).__name__} {exc}")
        try:
            stats["xobject_blocks_removed"] += clean_xobjects(page.get("/Resources"), size_cap)
        except Exception:
            pass
        writer.add_page(page)
        stats["pages"] += 1

    with open(dst, "wb") as fh:
        writer.write(fh)
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("dst", type=Path)
    args = ap.parse_args()
    print(clean_pdf(args.src, args.dst))
