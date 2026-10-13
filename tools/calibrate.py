#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Apply human-verified question overrides and create exact source-page crops.

Calibration files live in ``data/calibrations/*.json``.  They are deliberately
kept separate from the automatic parser so a future parser improvement cannot
silently undo a page-by-page verification.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


VALID_REVIEW_STATUSES = {"未校对", "题干已校对", "解析已校对"}


def crop_source_image(site_dir: Path, paper: dict, qid: str, index: int, spec: dict) -> str:
    page = int(spec["page"])
    source = site_dir / "assets" / "pages" / paper["slug"] / f"p{page:02d}.png"
    if not source.exists():
        raise FileNotFoundError(f"missing rendered source page: {source}")

    page_size = paper.get("page_size") or {}
    pdf_w = float(page_size.get("width") or 0)
    pdf_h = float(page_size.get("height") or 0)
    if not pdf_w or not pdf_h:
        raise ValueError(f"{paper['slug']} has no usable page_size")

    with Image.open(source) as image:
        sx, sy = image.width / pdf_w, image.height / pdf_h
        left = max(0, round(float(spec.get("left", 55)) * sx))
        right = min(image.width, round(float(spec.get("right", pdf_w - 55)) * sx))
        top = max(0, round(float(spec["top"]) * sy))
        bottom = min(image.height, round(float(spec["bottom"]) * sy))
        if right - left < 120 or bottom - top < 60:
            raise ValueError(f"invalid crop for {qid}: {spec}")
        cropped = image.crop((left, top, right, bottom)).convert("RGB")

    rel = f"assets/question-source/{qid}-{index:02d}.png"
    output = site_dir / rel
    output.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(output, optimize=True)
    return rel


def apply_calibration(calibration_path: Path, data_dir: Path, site_dir: Path) -> int:
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    slug = calibration["slug"]
    question_path = data_dir / "questions" / f"{slug}.json"
    if not question_path.exists():
        raise FileNotFoundError(f"parsed question file missing: {question_path}")

    paper = json.loads(question_path.read_text(encoding="utf-8"))
    questions = {q["id"]: q for q in paper.get("questions", [])}
    overrides = calibration.get("questions", [])
    expected_ids = set(calibration.get("expected_question_ids", []))
    actual_ids = set(questions)
    if expected_ids and expected_ids != actual_ids:
        missing = sorted(expected_ids - actual_ids)
        extra = sorted(actual_ids - expected_ids)
        raise ValueError(f"{slug} question IDs changed; missing={missing}, extra={extra}")

    touched: set[str] = set()
    for override in overrides:
        qid = override["id"]
        if qid not in questions:
            raise KeyError(f"calibration refers to unknown question ID: {qid}")
        patch = dict(override.get("patch", {}))
        status = patch.get("review_status")
        if status not in VALID_REVIEW_STATUSES:
            raise ValueError(f"{qid} has invalid review_status: {status!r}")
        questions[qid].update(patch)
        crops = override.get("source_crops", [])
        if not crops:
            raise ValueError(f"{qid} has no complete source crop specification")
        questions[qid]["source_images"] = [
            crop_source_image(site_dir, paper, qid, index, spec)
            for index, spec in enumerate(crops, start=1)
        ]
        touched.add(qid)

    if expected_ids and touched != expected_ids:
        raise ValueError(f"{slug} calibration coverage is incomplete: {sorted(expected_ids - touched)}")

    paper["calibration"] = {
        "version": calibration["version"],
        "updated_at": calibration["updated_at"],
        "source": calibration.get("source", "原 PDF 逐页人工核对"),
        "question_count": len(touched),
    }
    qs = paper.get("questions", [])
    paper["stats"] = {
        "total": len(qs),
        "with_answer": sum(bool(q.get("answer")) for q in qs),
        "with_explanation": sum(bool(q.get("explanation") or q.get("answer_blocks")) for q in qs),
        "with_figure": sum(bool(q.get("figures") or q.get("source_images")) for q in qs),
    }
    question_path.write_text(json.dumps(paper, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(touched)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--calibrations", type=Path, default=Path("data/calibrations"))
    args = parser.parse_args()

    total = 0
    for path in sorted(args.calibrations.glob("*.json")):
        count = apply_calibration(path, args.data, args.site)
        total += count
        print(f"[calibrate] {path.name}: {count} questions")
    print(f"[calibrate] complete: {total} questions")


if __name__ == "__main__":
    main()
