#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
题库 MCP 服务端（stdio，JSON-RPC 2.0，无第三方依赖）。

让 ChatGPT Desktop / Codex / Claude 等支持 MCP 的客户端直接"查题"：

    codex mcp add 数模电真题库 -- python <绝对路径>/tools/mcp_server.py

暴露的工具：
    list_papers      列出全部试卷
    search_questions 关键词检索题目（可按学校、年份过滤）
    get_question     取某份试卷的某一道题（含答案与解析）
    get_paper        取整份试卷
    list_tags        知识点清单
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "questions"
PROTOCOL_FALLBACK = "2024-11-05"
SITE_URL = "https://jsidiaowojd-hash.github.io/electronics-exam-bank"


def q_url(qid: str) -> str:
    return f"{SITE_URL}/question/{qid}.html"


def load_papers() -> dict[str, dict]:
    papers = {}
    for path in sorted(DATA.glob("*.json")):
        if path.name == "index.json":
            continue
        try:
            papers[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
    return papers


PAPERS = load_papers()


def paper_title(paper: dict) -> str:
    school = paper.get("school") or "未知学校"
    code = paper.get("code") or ""
    year = paper.get("year")
    return f"{school} {code} {year or ''} 电子技术".strip()


def brief(paper: dict, q: dict) -> dict:
    return {
        "question_id": q.get("id"),
        "url": q_url(q.get("id", "")),
        "paper_slug": paper["slug"],
        "paper": paper_title(paper),
        "number": q["number"],
        "type": q.get("type"),
        "section": q.get("section"),
        "stem": q["stem"][:300],
        "answer": q.get("answer"),
        "difficulty": q.get("difficulty"),
        "tags": q.get("tags", []),
        "has_figure": bool(q.get("figures")),
        "confidence": q.get("confidence"),
    }


def tool_list_papers(_args: dict) -> dict:
    return {
        "papers": [
            {
                "slug": p["slug"],
                "school": p.get("school"),
                "code": p.get("code"),
                "year": p.get("year"),
                "questions": p.get("stats", {}).get("total", 0),
                "with_answer": p.get("stats", {}).get("with_answer", 0),
                "pages": p.get("page_count"),
            }
            for p in sorted(PAPERS.values(), key=lambda x: (-(x.get("year") or 0), x["slug"]))
        ]
    }


def tool_search_questions(args: dict) -> dict:
    query = (args.get("query") or "").strip()
    school = args.get("school")
    year = args.get("year")
    limit = int(args.get("limit") or 12)
    terms = [t for t in re.split(r"\s+", query.lower()) if t]

    hits = []
    for paper in PAPERS.values():
        if school and school not in (paper.get("school") or ""):
            continue
        if year and int(year) != paper.get("year"):
            continue
        for q in paper["questions"]:
            hay = " ".join(
                [
                    q["stem"],
                    " ".join(o.get("text", "") for o in q.get("options", [])),
                    q.get("answer") or "",
                    q.get("explanation") or "",
                    " ".join(q.get("tags", [])),
                    paper_title(paper),
                ]
            ).lower()
            score = 0
            for t in terms:
                c = hay.count(t)
                if c:
                    score += c
                    if t in q["stem"].lower():
                        score += 3
            if terms and score == 0:
                continue
            hits.append((score, paper, q))
    hits.sort(key=lambda x: -x[0])
    return {"count": len(hits), "results": [brief(p, q) for _, p, q in hits[:limit]]}


def _find_paper(slug: str) -> dict | None:
    if slug in PAPERS:
        return PAPERS[slug]
    for paper in PAPERS.values():
        if paper["slug"] == slug:
            return paper
    for paper in PAPERS.values():  # 模糊匹配，例如只给 "zsu-885"
        if slug and slug in paper["slug"]:
            return paper
    return None


def tool_get_question(args: dict) -> dict:
    qid = str(args.get("question_id") or "").strip()
    if qid:
        for paper in PAPERS.values():
            for q in paper["questions"]:
                if q.get("id") == qid:
                    return {
                        "paper": paper_title(paper),
                        "slug": paper["slug"],
                        "url": q_url(qid),
                        "question": q,
                        "note": "confidence 不为 high 时，答案或选项由 PDF 自动切分而来，请谨慎引用。",
                    }
        return {"error": f"没有这个题目 ID：{qid}"}
    paper = _find_paper(str(args.get("slug") or ""))
    if not paper:
        return {"error": "没找到这份试卷，先用 list_papers 看一下 slug"}
    number = int(args.get("number") or 0)
    for q in paper["questions"]:
        if q["number"] == number:
            return {
                "paper": paper_title(paper),
                "slug": paper["slug"],
                "url": q_url(q.get("id", "")),
                "question": q,
                "note": "confidence 不为 high 时，答案或选项可能由 PDF 自动切分而来，请谨慎引用。",
            }
    return {"error": f"{paper['slug']} 里没有第 {number} 题"}


def tool_get_paper(args: dict) -> dict:
    paper = _find_paper(str(args.get("slug") or ""))
    if not paper:
        return {"error": "没找到这份试卷，先用 list_papers 看一下 slug"}
    include_answers = bool(args.get("include_answers", True))
    questions = []
    for q in paper["questions"]:
        item = {
            "number": q["number"],
            "type": q.get("type"),
            "stem": q["stem"],
            "options": q.get("options", []),
            "tags": q.get("tags", []),
            "figures": q.get("figures", []),
            "confidence": q.get("confidence"),
        }
        if include_answers:
            item["answer"] = q.get("answer")
            item["explanation"] = q.get("explanation")
        questions.append(item)
    return {
        "paper": paper_title(paper),
        "slug": paper["slug"],
        "page_count": paper.get("page_count"),
        "stats": paper.get("stats"),
        "questions": questions,
    }


def tool_list_tags(_args: dict) -> dict:
    counter: dict[str, int] = {}
    for paper in PAPERS.values():
        for q in paper["questions"]:
            for tag in q.get("tags", []):
                counter[tag] = counter.get(tag, 0) + 1
    return {"tags": dict(sorted(counter.items(), key=lambda kv: -kv[1]))}


TOOLS = [
    {
        "name": "list_papers",
        "description": "列出题库里全部试卷（学校、科目代码、年份、题量、含答案解析数量）。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_questions",
        "description": "按关键词检索数模电考研真题，返回题干、答案摘要与知识点。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "关键词，如“共射放大电路 静态工作点”"},
                "school": {"type": "string", "description": "可选，按学校过滤，如“中山大学”"},
                "year": {"type": "integer", "description": "可选，按年份过滤，如 2024"},
                "limit": {"type": "integer", "description": "返回条数，默认 12"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_question",
        "description": "取某一道题的完整内容（选项、答案、解析、配图），并给出稳定的单题链接。"
                       "既可以用题目 ID 精确取，也可以按试卷 slug + 题号取。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question_id": {"type": "string", "description": "题目 ID，如 zsu-885-2024-p1-q11"},
                "slug": {"type": "string", "description": "试卷标识，如 zsu-885-2024"},
                "number": {"type": "integer", "description": "题号"},
            },
        },
    },
    {
        "name": "get_paper",
        "description": "取整份试卷的全部题目。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string"},
                "include_answers": {"type": "boolean", "description": "是否包含答案与解析，默认 true"},
            },
            "required": ["slug"],
        },
    },
    {
        "name": "list_tags",
        "description": "列出全部知识点及题目数量，便于按知识点刷题。",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

HANDLERS = {
    "list_papers": tool_list_papers,
    "search_questions": tool_search_questions,
    "get_question": tool_get_question,
    "get_paper": tool_get_paper,
    "list_tags": tool_list_tags,
}


def send(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(request: dict) -> dict | None:
    method = request.get("method")
    rid = request.get("id")

    if method == "initialize":
        params = request.get("params") or {}
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {
                "protocolVersion": params.get("protocolVersion") or PROTOCOL_FALLBACK,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "数模电考研真题库", "version": "1.0.0"},
                "instructions": (
                    f"本地数模电考研真题库，共 {len(PAPERS)} 份试卷。"
                    "先用 list_papers 看有哪些卷子，再 search_questions 找题，"
                    "get_question 拿答案与解析。"
                ),
            },
        }
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        handler = HANDLERS.get(name)
        if handler is None:
            return {
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": -32602, "message": f"未知工具：{name}"},
            }
        try:
            result = handler(args)
            text = json.dumps(result, ensure_ascii=False, indent=1)
            return {
                "jsonrpc": "2.0",
                "id": rid,
                "result": {"content": [{"type": "text", "text": text}], "isError": False},
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": rid,
                "result": {
                    "content": [{"type": "text", "text": f"执行失败：{exc}"}],
                    "isError": True,
                },
            }
    if rid is not None:
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "error": {"code": -32601, "message": f"不支持的方法：{method}"},
        }
    return None


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle(request)
        if response is not None:
            send(response)


if __name__ == "__main__":
    main()
