# -*- coding: utf-8 -*-
"""把连接关系 JSON 生成 KiCad 8 原理图。

用法：
    python scripts/netlist_to_sch.py out/arduino_min_system_netlist.json
    python scripts/netlist_to_sch.py out/xxx_netlist.json --out out/xxx.kicad_sch

生成后可直接用 KiCad 打开。再用 kicad-cli 反导网表，可以和源 JSON 对账：
    kicad-cli sch export netlist --output out/check.net out/xxx.kicad_sch
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import sch_writer  # noqa: E402


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description="连接关系 JSON -> KiCad 原理图")
    parser.add_argument("netlist", help="连接关系 JSON 路径")
    parser.add_argument("--out", default="", help="输出 .kicad_sch 路径")
    args = parser.parse_args()

    src = Path(args.netlist)
    if not src.exists():
        print("[FAIL] 文件不存在：%s" % src)
        return 2

    netlist = json.loads(src.read_text(encoding="utf-8"))
    board = (netlist.get("board") or {}).get("name", "board")
    out_path = Path(args.out) if args.out else src.parent / ("%s.kicad_sch" % board)

    print("=" * 68)
    print(" 生成原理图：%s" % board)
    print("=" * 68)

    try:
        warnings = sch_writer.netlist_to_file(netlist, out_path, project_name="pcb-agent")
    except RuntimeError as exc:
        print("[FAIL] %s" % exc)
        return 1

    for w in warnings:
        print("[WARN] %s" % w)

    size = out_path.stat().st_size
    print("器件 %d 个，网络 %d 个"
          % (len(netlist.get("components", [])), len(netlist.get("nets", []))))
    print()
    print("已生成：%s（%.1f KB）" % (out_path, size / 1024))
    print()
    print("下一步：用 KiCad 打开它，或反导网表对账：")
    print('  kicad-cli sch export netlist --output out/check.net "%s"' % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
