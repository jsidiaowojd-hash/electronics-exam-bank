#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把入库后的逐页文本切成"一道一道题"，并接上答案解析、图形、知识点标签。

输入：data/papers/<slug>.json
输出：data/questions/<slug>.json     结构化题目（机器可读，供站点与 ChatGPT 查询）
      data/questions/index.json      全站题库索引

自动切题不保证 100% 准确，所以每条题目都带 confidence 字段：
  high   —— 题干、选项、答案都对上了
  medium —— 切出来了但答案或选项缺失
  low    —— 只有题干，需要人工校对
人工校对方式：直接改 data/questions/<slug>.json，站点重新构建即可。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest import strip_ads  # noqa: E402  复用同一套广告文案清洗规则

# ------------------------------------------------------------------ 正则

PART_RE = re.compile(r"^第\s*[一二三四五]\s*部分")
SECTION_RE = re.compile(
    r"^[（(]?[一二三四五六七八九十]+\s*[、.．)）]\s*"
    r"(选择题|填空题|判断题|简答题|计算题|计算分析题|分析题|综合题|作图题|设计题|问答题|应用题)"
)
Q_START_RE = re.compile(r"^[（(]?\s*(\d{1,2})\s*[、.．,，)）]\s*(\S.*)?$")
CN_NUM = {c: i + 1 for i, c in enumerate("一二三四五六七八九十")}
CN_START_RE = re.compile(r"^[（(]?\s*([一二三四五六七八九十]{1,3})\s*[、.．)）]\s*(\S.*)?$")
OPTION_RE = re.compile(r"^[（(]?\s*([A-DＡ-Ｄ])\s*[、.．,，)）:：]?\s*(.*)$")
SUBNUM_RE = re.compile(r"^[（(]?\s*\d{1,2}\s*[)）]\s*\S")
ANSWER_RE = re.compile(
    r"^[（(]?(?:题)?\s*([一二三四五六七八九十]{1,3}|\d{1,2})\s*[、.．]?\s*解\s*[:：]?\s*(.*)$"
)
EXPLAIN_RE = re.compile(r"^解\s*析\s*[:：]?\s*(.*)$")
JUAN_RE = re.compile(r"真题详解|参考答案|答案解析|试题解析|答案与解析")

# ------------------------------------------------------------------ 知识点标签

TAG_RULES: list[tuple[str, str, list[str]]] = [
    ("模拟电子技术", "半导体器件", ["二极管", "稳压管", "三极管", "晶体管", "场效应管", "PN结"]),
    ("模拟电子技术", "基本放大电路", ["共射", "共集", "共基", "共源", "静态工作点", "Q点", "失真"]),
    ("模拟电子技术", "多级放大电路", ["多级放大", "级联", "差分放大", "差动放大", "零点漂移"]),
    ("模拟电子技术", "频率响应", ["频率响应", "高频特性", "低频特性", "截止频率", "fT", "通频带"]),
    ("模拟电子技术", "反馈放大电路", ["负反馈", "正反馈", "反馈类型", "深度负反馈", "闭环增益"]),
    ("模拟电子技术", "运算放大器", ["理想运放", "运算电路", "运放", "虚短", "虚断", "减法电路", "加法电路", "积分电路", "微分电路"]),
    ("模拟电子技术", "有源滤波", ["滤波器", "低通", "高通", "带通"]),
    ("模拟电子技术", "波形发生", ["振荡", "正弦波", "方波", "三角波", "文氏桥", "RC桥", "石英晶体"]),
    ("模拟电子技术", "功率放大", ["功率放大", "功放", "互补对称", "OCL", "OTL", "交越失真"]),
    ("模拟电子技术", "直流电源", ["整流", "滤波", "稳压", "串联型", "开关电源", "三端稳压"]),
    ("数字电子技术", "逻辑代数", ["逻辑函数", "真值表", "卡诺图", "化简", "最小项", "无关项", "逻辑门"]),
    ("数字电子技术", "组合逻辑电路", ["组合逻辑", "编码器", "译码器", "数据选择器", "加法器", "竞争冒险"]),
    ("数字电子技术", "触发器", ["触发器", "RS触发器", "JK触发器", "D触发器", "边沿触发", "主从"]),
    ("数字电子技术", "时序逻辑电路", ["时序逻辑", "状态图", "状态方程", "计数器", "移位寄存器", "寄存器", "同步时序"]),
    ("数字电子技术", "存储器与可编程器件", ["RAM", "ROM", "存储器", "PLA", "PAL", "FPGA"]),
    ("数字电子技术", "脉冲波形产生", ["555", "施密特", "单稳态", "多谐振荡", "整形"]),
    ("数字电子技术", "AD/DA转换", ["A/D", "D/A", "ADC", "DAC", "转换器", "量化"]),
]

QUESTION_TYPE_BY_SECTION = {
    "选择题": "choice",
    "填空题": "fill",
    "判断题": "judge",
    "计算题": "calc",
    "计算分析题": "calc",
    "分析题": "analysis",
    "简答题": "short",
    "问答题": "short",
    "综合题": "calc",
    "作图题": "draw",
    "设计题": "design",
    "应用题": "calc",
}


def derive_tags(text: str) -> list[str]:
    tags = []
    for _group, tag, words in TAG_RULES:
        if any(w in text for w in words):
            tags.append(tag)
    return tags


def normalize_number(tok: str) -> int | None:
    try:
        return int(tok)
    except ValueError:
        return cn_number(tok)


def cn_number(tok: str) -> int | None:
    if not tok:
        return None
    tok = tok.strip()
    if len(tok) == 1:
        return CN_NUM.get(tok)
    if tok.startswith("十"):
        rest = CN_NUM.get(tok[1:], 0) if len(tok) > 1 else 0
        return 10 + rest
    if tok.endswith("十"):
        return CN_NUM.get(tok[0], 0) * 10
    if len(tok) >= 3 and tok[1] == "十":
        return CN_NUM.get(tok[0], 0) * 10 + CN_NUM.get(tok[2], 0)
    return None


# ------------------------------------------------------------------ 切分

def split_questions(paper: dict) -> dict:
    lines: list[dict] = []
    for page in paper["pages"]:
        for line in page["lines"]:
            lines.append({**line, "page": page["n"]})

    questions: list[dict] = []
    explanations: dict[int, list[str]] = {}
    part = ""
    section = ""
    expected = 1
    expected_cn = 1
    num_style = None  # 'digit' | 'cn'
    answer_cursor = 0
    current = None
    answers_started = False
    answer_buffer: list[str] | None = None
    answer_num: int | None = None
    answer_marks: list[dict] | None = None

    def close(current_q):
        if current_q and (current_q["stem_lines"] or current_q["figures"]):
            questions.append(current_q)

    for line in lines:
        text = line["text"].strip()
        if not text:
            continue

        # 详解部分的标志：出现"题N解：/N、解："这类行，且已经收集到若干道题
        m_ans = ANSWER_RE.match(text)
        if not answers_started and m_ans and len(questions) >= 3:
            answers_started = True
            if current:
                close(current)
                current = None

        if PART_RE.match(text) or SECTION_RE.match(text):
            m = PART_RE.match(text)
            if m:
                part = text
                # 换部分时题号重新计数（各校第二部分常从 1 重新编号）
                if current:
                    close(current)
                    current = None
                if not answers_started:
                    expected = 1
                    expected_cn = 1
                    num_style = None
            m2 = SECTION_RE.match(text)
            if m2:
                section = m2.group(1)
                if current:
                    close(current)
                    current = None
                if not answers_started:
                    expected = 1
                    expected_cn = 1
                    num_style = None
            continue

        # 详解部分：题N解：xxx / 解析：xxx
        if answers_started and m_ans:
            num = normalize_number(m_ans.group(1))
            target = None
            for q in questions:
                if q["number"] == num and q["answer"] is None:
                    target = q
                    break
            if target is None:
                # 编号在各部分重新开始的卷子：按出现顺序接下一道还没答案的题
                for q in questions[answer_cursor:]:
                    if q.get("answer") is None:
                        target = q
                        break
            if target is None:
                # 宁可空着，也不要把解析安到别的题上
                target = None
            else:
                answer_cursor = questions.index(target)
            if target is not None:
                raw_answer = (m_ans.group(2) or "").strip()
                target.setdefault("explanation_lines", [])
                if raw_answer and re.fullmatch(r"[（(].{0,80}[）)]", raw_answer):
                    # 括号里是命题点评，不是答案，挪进解析
                    target["explanation_lines"].append(raw_answer.strip("（）()"))
                    raw_answer = ""
                target["answer"] = raw_answer or None
                answer_num = num
                answer_buffer = target["explanation_lines"]
                answer_marks = target.setdefault("explanation_marks", [])
                answer_marks.append(
                    {"page": line["page"], "top": line["top"], "bottom": line["bottom"]}
                )
            else:
                answer_buffer, answer_num = None, None
            continue

        m_exp = EXPLAIN_RE.match(text)
        if answers_started and m_exp and answer_buffer is not None:
            answer_buffer.append(m_exp.group(1).strip())
            if answer_marks is not None:
                answer_marks.append({"page": line["page"], "top": line["top"], "bottom": line["bottom"]})
            continue

        if answers_started:
            if answer_buffer is not None:
                if re.fullmatch(r"[-—\s]{6,}", text) or set(text) <= set("-—="):
                    answer_buffer, answer_num = None, None
                    answer_marks = None
                    continue
                answer_buffer.append(text)
                if answer_marks is not None:
                    answer_marks.append(
                        {"page": line["page"], "top": line["top"], "bottom": line["bottom"]}
                    )
            continue

        # 题干/选项
        m_cn = CN_START_RE.match(text)
        if m_cn:
            cnum = cn_number(m_cn.group(1))
            # 从数字编号切到「一、二、三」体例时，第一道大题不管序号是多少都算新题
            starts_new = cnum is not None and (
                cnum == expected_cn or (num_style != "cn" and current is not None)
            )
            if starts_new and not OPTION_RE.match(text):
                if num_style != "cn" and section == "选择题":
                    section = ""  # 「一、选择题」后面接的"二、三…"是大题，别再挂着选择题的名
                close(current)
                current = {
                    "number": cnum,
                    "page": line["page"],
                    "first_line_top": line["top"],
                    "y_top": line["top"],
                    "y_bottom": line["bottom"],
                    "stem_lines": [f"{m_cn.group(1)}、{(m_cn.group(2) or '').strip()}".strip("、")],
                    "options": [],
                    "figures": [],
                    "part": part,
                    "section": section,
                    "answer": None,
                }
                expected_cn = cnum + 1
                num_style = "cn"
                if not (m_cn.group(2) or "").strip():
                    current["stem_lines"] = []
                continue

        m_q = Q_START_RE.match(text)
        if m_q and not OPTION_RE.match(text):
            num = int(m_q.group(1))
            parenthesized = text.lstrip().startswith(("（", "("))
            if num_style == "cn" and parenthesized:
                current["stem_lines"].append(text)
                current["y_bottom"] = line["bottom"]
                continue
            if num == expected or (current and num_style != "cn" and num == current["number"] + 1):
                close(current)
                current = {
                    "number": num,
                    "page": line["page"],
                    "first_line_top": line["top"],
                    "y_top": line["top"],
                    "y_bottom": line["bottom"],
                    "stem_lines": [],
                    "options": [],
                    "figures": [],
                    "part": part,
                    "section": section,
                    "answer": None,
                }
                expected = num + 1
                num_style = "digit"
                head = (m_q.group(2) or "").strip()
                if head:
                    current["stem_lines"].append(head)
                continue
            # 题号回落：第二部分/另一组题重新从 1 开始编号
            if (
                num == 1
                and current is not None
                and not parenthesized
                and len(current["stem_lines"]) > 3
            ):
                close(current)
                current = {
                    "number": 1,
                    "page": line["page"],
                    "first_line_top": line["top"],
                    "y_top": line["top"],
                    "y_bottom": line["bottom"],
                    "stem_lines": [],
                    "options": [],
                    "figures": [],
                    "part": part,
                    "section": section,
                    "answer": None,
                }
                expected = 2
                num_style = "digit"
                head = (m_q.group(2) or "").strip()
                if head:
                    current["stem_lines"].append(head)
                continue

        if current is None:
            continue

        m_opt = OPTION_RE.match(text)
        if m_opt and current["section"] == "选择题":
            label = m_opt.group(1).upper().replace("Ａ", "A").replace("Ｂ", "B")
            label = {"Ａ": "A", "Ｂ": "B", "Ｃ": "C", "Ｄ": "D"}.get(m_opt.group(1), label)
            body = (m_opt.group(2) or "").strip()
            if current["options"] and current["options"][-1]["label"] == label:
                current["options"][-1]["text"] += " " + body
            else:
                current["options"].append({"label": label, "text": body})
            continue

        current["stem_lines"].append(text)
        current["y_bottom"] = line["bottom"]

    close(current)

    # 图形挂载：取同页中最靠近它上方的那道题；没有则给本页第一题或上一题
    for page in paper["pages"]:
        page_qs = [q for q in questions if q["page"] == page["n"]]
        for fig in page["figures"]:
            best, best_top = None, -1.0
            for q in page_qs:
                top = q.get("first_line_top", 0.0)
                if top <= fig["top"] and top > best_top:
                    best, best_top = q, top
            if best is None and page_qs:
                best = page_qs[0]
            if best is None:
                before = [q for q in questions if q["page"] < page["n"]]
                best = before[-1] if before else None
            if best is not None:
                best["figures"].append(fig["file"])

    for q in questions:
        q.pop("first_line_top", None)
    for q in questions:
        q["explanation"] = "\n".join(q.get("explanation_lines", [])).strip()
        q.pop("explanation_lines", None)
        # 把解析占据的版面位置合并成连续区块，供建站时裁原图
        blocks: list[dict] = []
        for mark in q.get("explanation_marks", []):
            if (
                blocks
                and blocks[-1]["page"] == mark["page"]
                and mark["top"] - blocks[-1]["bottom"] <= 45
            ):
                blocks[-1]["bottom"] = max(blocks[-1]["bottom"], mark["bottom"])
            else:
                blocks.append({"page": mark["page"], "top": mark["top"], "bottom": mark["bottom"]})
        q["answer_blocks"] = blocks
        q.pop("explanation_marks", None)
    return {"questions": questions, "explanations": explanations}


def finalize(paper: dict, parsed: dict) -> dict:
    out = {
        "slug": paper["slug"],
        "school": paper["school"],
        "school_slug": paper["school_slug"],
        "code": paper["code"],
        "year": paper["year"],
        "source_pdf": paper.get("source_pdf"),
        "clean_note": paper.get("clean_note", ""),
        "page_count": len(paper["pages"]),
        "scan_style": paper.get("scan_style", False),
        "page_size": {
            "width": paper["pages"][0].get("width") if paper["pages"] else None,
            "height": paper["pages"][0].get("height") if paper["pages"] else None,
        },
        "questions": [],
    }
    for q in parsed["questions"]:
        stem = strip_ads(" ".join(q["stem_lines"])).strip()
        stem = re.sub(r"\s{2,}", " ", stem)
        explanation = strip_ads(q.get("explanation", "")).strip()
        explanation = re.sub(r"[ \t]{2,}", " ", explanation)
        tags = derive_tags(stem + " " + " ".join(o["text"] for o in q["options"]))
        qtype = QUESTION_TYPE_BY_SECTION.get(q["section"] or "", "other")
        if q["options"] and qtype == "other":
            qtype = "choice"
        elif qtype == "other":
            qtype = "calc"  # 华科这类卷子：整卷都是大题
        item = {
            "id": f"{paper['slug']}-{q['number']:02d}",
            "number": q["number"],
            "part": q["part"],
            "section": q["section"],
            "type": qtype,
            "stem": stem,
            "options": [
                {"label": o["label"], "text": strip_ads(o["text"]).strip()} for o in q["options"]
            ],
            "figures": q["figures"],
            "answer": strip_ads(q["answer"] or "").strip() or None,
            "explanation": explanation,
            "answer_blocks": q.get("answer_blocks", []),
            "tags": tags,
            "page": q["page"],
            "y_top": q.get("y_top"),
            "y_bottom": q.get("y_bottom"),
        }
        confidence = "low"
        if item["answer"]:
            confidence = "high" if (item["options"] or item["type"] != "choice") else "medium"
        elif explanation and len(explanation) > 30:
            confidence = "high"  # 大题只有解析、没有单独的"答案"是正常的
        elif item["options"]:
            confidence = "medium"
        item["confidence"] = confidence
        out["questions"].append(item)
    out["stats"] = {
        "total": len(out["questions"]),
        "with_answer": sum(1 for q in out["questions"] if q["answer"]),
        "with_explanation": sum(1 for q in out["questions"] if q["explanation"]),
        "with_figure": sum(1 for q in out["questions"] if q["figures"]),
    }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data"))
    args = ap.parse_args()

    papers_dir = args.data / "papers"
    out_dir = args.data / "questions"
    out_dir.mkdir(parents=True, exist_ok=True)

    index = []
    for path in sorted(papers_dir.glob("*.json")):
        paper = json.loads(path.read_text(encoding="utf-8"))
        parsed = split_questions(paper)
        record = finalize(paper, parsed)
        (out_dir / f"{record['slug']}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        s = record["stats"]
        print(
            f"[parse] {record['slug']:20s} 题目={s['total']:3d} 有答案={s['with_answer']:3d} "
            f"带图={s['with_figure']:3d} 页码={record['page_count']}"
        )
        index.append(
            {
                "slug": record["slug"],
                "school": record["school"],
                "code": record["code"],
                "year": record["year"],
                "questions": s["total"],
                "with_answer": s["with_answer"],
                "pages": record["page_count"],
            }
        )

    (out_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"\n共解析 {len(index)} 份试卷 -> {out_dir}")


if __name__ == "__main__":
    main()
