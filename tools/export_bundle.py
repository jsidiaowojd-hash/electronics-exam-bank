#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把整个题库导出成"单个文件"，用于直接丢给 ChatGPT / 任何聊天窗口测试它能不能读。

输出：ChatGPT可直接读/数模电考研真题库.md   —— 一个文件装下全部题目、答案、解析、知识点
      ChatGPT可直接读/怎么测.md             —— 附带的测试问题清单

用法：python tools/export_bundle.py --data data --out "ChatGPT可直接读"
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

SITE = "https://jsidiaowojd-hash.github.io/electronics-exam-bank"

HEAD = """# 数模电考研真题库（模拟电子技术 + 数字电子技术）

本文件是"数模电考研真题库"的完整导出，供 ChatGPT 等模型直接阅读。
内容整理自公开流传的历年考研真题 PDF，解析版权归原作者，仅供个人复习使用。

数据规模：{n_papers} 份试卷 / {n_q} 道题 / {n_a} 道有答案 / {n_e} 道有解析 / {n_f} 处配图。

每道题都有一个稳定的单题页地址，格式：
    https://jsidiaowojd-hash.github.io/electronics-exam-bank/question/<question_id>.html
题目 ID 规则：<试卷 slug>-q<题号>；卷内分「部分」时加 -p<部分序号>；
用「一、二、三」编号的大题用 -c<序号>（例：zsu-885-2024-p1-c2）。
正文里每道题都会给出它的 question_id 和这个链接。

每道题的字段说明：
- 题号、题型（choice 选择题 / fill 填空 / calc 大题 / analysis 分析）
- 题干（来自 PDF 文字层，公式的上下标会散成多行，属于正常现象）
- 选项（选择题才有）
- 配图（站内 PNG 路径；本文件中的题目如有配图会标注）
- 答案、解析
- 知识点标签（用于按考点归类）
- 置信度：high 表示切分可靠；medium / low 表示由 PDF 自动切分，答案或选项可能有缺漏

---

## 一、试卷清单

"""


def load_local(data_dir: Path) -> list[dict]:
    papers = []
    for path in sorted((data_dir / "questions").glob("*.json")):
        if path.name == "index.json":
            continue
        papers.append(json.loads(path.read_text(encoding="utf-8")))
    papers.sort(key=lambda p: (-(p.get("year") or 0), p.get("slug", "")))
    return papers


def load_api() -> list[dict]:
    """从线上接口取数，保证附件和网站内容一致（含 CI 收录的全部卷子）。"""
    import urllib.request

    def get(path: str):
        with urllib.request.urlopen(SITE + path, timeout=60) as resp:
            return json.loads(resp.read().decode())

    meta = {p["slug"]: p for p in get("/api/papers.json")["papers"]}
    grouped: dict[str, list] = {}
    for q in get("/api/questions.json")["questions"]:
        grouped.setdefault(q["slug"], []).append(q)
    papers = []
    for slug, qs in grouped.items():
        m = meta.get(slug, {})
        papers.append(
            {
                "slug": slug,
                "school": m.get("school"),
                "code": m.get("code"),
                "year": m.get("year"),
                "page_count": m.get("page_count"),
                "stats": {
                    "total": len(qs),
                    "with_answer": sum(1 for q in qs if q.get("answer")),
                    "with_explanation": sum(1 for q in qs if q.get("explanation")),
                    "with_figure": sum(1 for q in qs if q.get("figures")),
                },
                "questions": sorted(qs, key=lambda q: (q.get("page") or 0, q["number"])),
            }
        )
    papers.sort(key=lambda p: (-(p.get("year") or 0), p.get("slug", "")))
    return papers


def build(data_dir: Path, out_dir: Path) -> dict:
    return render(load_local(data_dir), out_dir)


def build_from_api(out_dir: Path) -> dict:
    return render(load_api(), out_dir)


def render(papers: list[dict], out_dir: Path) -> dict:

    n_q = sum(p.get("stats", {}).get("total", 0) for p in papers)
    n_a = sum(p.get("stats", {}).get("with_answer", 0) for p in papers)
    n_e = sum(p.get("stats", {}).get("with_explanation", 0) for p in papers)
    n_f = sum(p.get("stats", {}).get("with_figure", 0) for p in papers)

    lines = [
        HEAD.format(
            n_papers=len(papers), n_q=n_q, n_a=n_a, n_e=n_e, n_f=n_f
        ).rstrip()
    ]
    for p in papers:
        s = p.get("stats", {})
        title = f"{p.get('school') or '未知学校'} {p.get('code') or ''} {p.get('year') or ''} 电子技术".strip()
        lines.append(
            f"- **{title}**（{p['slug']}）：{s.get('total', 0)} 题，"
            f"答案 {s.get('with_answer', 0)}，解析 {s.get('with_explanation', 0)}，"
            f"配图 {s.get('with_figure', 0)}，原卷 {p.get('page_count')} 页"
        )

    lines.append("\n---\n\n## 二、全部题目\n")
    for p in papers:
        title = f"{p.get('school') or '未知学校'} {p.get('code') or ''} {p.get('year') or ''} 电子技术".strip()
        lines.append(f"\n### {title}\n")
        for q in p["questions"]:
            section = q.get("section") or ""
            qid = q.get("id") or f"{p['slug']}-q{q['number']}"
            stars = q.get("difficulty_stars")
            lines.append(
                f"#### 第 {q['number']} 题（{section}，id: {qid}，"
                f"难度 {stars or '未标注'}，置信度 {q.get('confidence')}）"
            )
            lines.append(f"单题链接：{SITE}/question/{qid}.html")
            lines.append(q["stem"])
            for opt in q.get("options", []):
                lines.append(f"- {opt['label']}. {opt['text']}")
            if q.get("figures"):
                lines.append(f"（本题有 {len(q['figures'])} 张配图）")
            lines.append(f"**答案**：{q.get('answer') or '未收录'}")
            if q.get("explanation"):
                lines.append(f"**解析**：{q['explanation']}")
            lines.append(
                f"**知识点**：{'、'.join(q.get('tags', [])) or '未标注'}"
            )
            lines.append("")

    out_dir.mkdir(parents=True, exist_ok=True)
    bundle = out_dir / "数模电考研真题库.md"
    bundle.write_text("\n".join(lines), encoding="utf-8")
    # 同时给一份 .txt：有的客户端对 .md 的预览/上传更保守
    plain = out_dir / "数模电考研真题库.txt"
    plain.write_text("\n".join(lines), encoding="utf-8")

    howto = out_dir / "怎么测.md"
    # 分卷导出：每份试卷一个文件，方便先拿一份小文件试水
    per_paper_dir = out_dir / "分卷"
    per_paper_dir.mkdir(parents=True, exist_ok=True)
    for p in papers:
        title = f"{p.get('school') or '未知学校'} {p.get('code') or ''} {p.get('year') or ''} 电子技术".strip()
        chunk = [f"# {title}（{p['slug']}）", ""]
        for q in p["questions"]:
            qid = q.get("id") or f"{p['slug']}-q{q['number']}"
            chunk.append(
                f"## 第 {q['number']} 题（{q.get('section') or ''}，id: {qid}，"
                f"难度 {q.get('difficulty_stars') or '未标注'}）"
            )
            chunk.append(f"单题链接：{SITE}/question/{qid}.html")
            chunk.append(q["stem"])
            for opt in q.get("options", []):
                chunk.append(f"- {opt['label']}. {opt['text']}")
            if q.get("figures"):
                chunk.append(f"（本题有 {len(q['figures'])} 张配图）")
            chunk.append(f"**答案**：{q.get('answer') or '未收录'}")
            if q.get("explanation"):
                chunk.append(f"**解析**：{q['explanation']}")
            chunk.append(f"**知识点**：{'、'.join(q.get('tags', [])) or '未标注'}")
            chunk.append("")
        (per_paper_dir / f"{title}.md").write_text("\n".join(chunk), encoding="utf-8")

    howto.write_text(
        "\n".join(
            [
                "# 怎么验证 ChatGPT 能不能读这个题库",
                "",
                "## 第一步：把文件喂给它",
                "在 ChatGPT 输入框点回形针「上传文件」，选同目录下的「数模电考研真题库.md」；"
                "或者把这个文件从资源管理器直接拖进输入框。",
                "文件约 150 KB，一次读完。该目录下还有一份内容相同的 .txt 备用。",
                "**这一步不做，ChatGPT 只会跟你要文件，不会自己去找。**",
                "",
                "## 第二步：用这几句话测",
                "1. 这个文件里一共收录了几份试卷、多少道题？分别是哪些学校哪一年？",
                "2. 2024 年中山大学 885 第 1 题选什么？解析是什么？",
                "3. 帮我找出所有考「负反馈」的题目，列出题号和出处。",
                "4. 华中科技大学 831 的整卷有没有答案？没有的话解析里讲了什么？",
                "5. 把这些题按「模拟电子技术 / 数字电子技术」两个模块分类，各有多少道？",
                "",
                "## 第三步：看它答得对不对",
                "回答里如果出现了具体题号、选项和解析原文，说明它确实读进来了；"
                "如果只是泛泛而谈，那多半是没读到文件内容，并不是题库的问题。",
                "",
                "## 想让它联网抓整站（不止这一个文件）",
                "需要先把 site/ 部署到公网，再让它访问 /llms.txt。",
                "站点已经自动生成好了 llms.txt、api/questions.json、sitemap.xml，"
                "部署完把域名告诉它就行。",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "papers": len(papers),
        "questions": n_q,
        "bundle": bundle,
        "size_kb": round(bundle.stat().st_size / 1024),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--out", type=Path, default=Path("ChatGPT可直接读"))
    ap.add_argument("--from-url", action="store_true",
                    help="改为从线上接口取数（与网站内容完全一致，含 CI 收录的全部卷子）")
    args = ap.parse_args()
    stats = build_from_api(args.out) if args.from_url else build(args.data, args.out)
    print(
        f"[export] {stats['papers']} 份试卷 / {stats['questions']} 题 -> "
        f"{stats['bundle']} ({stats['size_kb']} KB)"
    )


if __name__ == "__main__":
    main()
