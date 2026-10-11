#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
站点自检：把 site/ 里所有 HTML 的链接、图片、JSON 接口过一遍，
确认没有断链、没有缺失素材、接口能被解析。

用法：python tools/check.py --site site
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from lxml import html as lxml_html

LINK_ATTRS = {"a": "href", "link": "href", "script": "src", "img": "src"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", type=Path, default=Path("site"))
    args = ap.parse_args()
    site: Path = args.site

    html_files = sorted(site.rglob("*.html"))
    checked = broken = external = 0
    problems: list[str] = []

    for path in html_files:
        doc = lxml_html.fromstring(path.read_text(encoding="utf-8"))
        for tag, attr in LINK_ATTRS.items():
            for node in doc.iter(tag):
                raw = node.get(attr)
                if not raw:
                    continue
                if raw.startswith(("http://", "https://", "mailto:", "data:")):
                    external += 1
                    continue
                target = urlparse(raw)
                rel = unquote(target.path)
                if not rel:
                    continue
                resolved = (path.parent / rel).resolve()
                checked += 1
                if not resolved.exists():
                    broken += 1
                    problems.append(f"{path.relative_to(site)} -> {raw}")

    print(f"HTML 页面      : {len(html_files)}")
    print(f"站内链接/图片  : {checked}（外部链接 {external}）")
    print(f"断链           : {broken}")
    if problems:
        print("\n前 20 条断链：")
        for item in problems[:20]:
            print("  -", item)

    print("\nJSON 接口：")
    for name in ["api/papers.json", "api/questions.json", "api/tags.json", "api/search-index.json"]:
        fp = site / name
        if not fp.exists():
            print(f"  ✗ 缺失 {name}")
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            size = fp.stat().st_size / 1024
            if isinstance(data, dict):
                detail = ", ".join(f"{k}={len(v) if isinstance(v, list) else v}" for k, v in list(data.items())[:3])
            else:
                detail = f"items={len(data)}"
            print(f"  ✓ {name}  {size:.0f} KB  ({detail})")
        except Exception as exc:
            print(f"  ✗ {name} 解析失败：{exc}")

    for name in ["llms.txt", "llms-full.txt", "sitemap.xml", "robots.txt", "openapi.yaml"]:
        fp = site / name
        print(f"  {'✓' if fp.exists() else '✗'} {name}  {fp.stat().st_size / 1024:.0f} KB" if fp.exists() else f"  ✗ 缺失 {name}")


if __name__ == "__main__":
    main()
