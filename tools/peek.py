#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""快速查看某份试卷的切分结果，方便人工校对。

用法：python tools/peek.py data/questions/zsu-885-2024.json [条数]
"""

import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
data = json.loads(path.read_text(encoding="utf-8"))

print(f"{data.get('school')} {data.get('code')} {data.get('year')} · "
      f"{data.get('stats')} · 原卷 {data.get('page_count')} 页")
for q in data["questions"][:limit]:
    opts = " / ".join(f"{o['label']}.{o['text'][:12]}" for o in q.get("options", []))
    print(f"\n#{q['number']:>2} [{q['type']}] 置信={q['confidence']} 答案={q.get('answer') or '-'} "
          f"图={len(q['figures'])} 页{q['page']} 标签={','.join(q['tags'])}")
    print("   题干:", q["stem"][:150].replace("\n", " "))
    if opts:
        print("   选项:", opts[:150])
    if q.get("explanation"):
        print("   解析:", q["explanation"][:120].replace("\n", " "))
