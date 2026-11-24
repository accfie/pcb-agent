# -*- coding: utf-8 -*-
"""校验连接关系 JSON 的结构是否合法。

校验逻辑在 src/netlist_check.py，MVP 流水线复用的也是同一份，
避免两处实现不一致。

用法：
    python scripts/check_netlist.py data/sample_netlist.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import netlist_check  # noqa: E402


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    if len(sys.argv) < 2:
        print("用法：python scripts/check_netlist.py <某个连接关系 JSON>")
        return 2

    path = Path(sys.argv[1])
    if not path.exists():
        print("[FAIL] 文件不存在：%s" % path)
        return 2

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print("[FAIL] JSON 语法错误：第 %d 行第 %d 列 —— %s" % (exc.lineno, exc.colno, exc.msg))
        print("       把这一行原文回喂给 LLM，让它修好再输出。")
        return 1

    errors, warnings = netlist_check.validate(data)

    print("=" * 60)
    print("校验文件：%s" % path.name)
    print("=" * 60)
    print("器件 %d 个，网络 %d 个"
          % (len(data.get("components") or []), len(data.get("nets") or [])))

    for msg in warnings:
        print("[WARN] %s" % msg)
    for msg in errors:
        print("[FAIL] %s" % msg)

    print("-" * 60)
    if errors:
        print("结论：%d 个错误、%d 个警告 —— 结构不合法，需重新生成。"
              % (len(errors), len(warnings)))
        return 1
    print("结论：结构合法，%d 个警告。" % len(warnings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
