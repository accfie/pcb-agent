# -*- coding: utf-8 -*-
"""原理图对账：用 kicad-cli 把生成的 .kicad_sch 反导成网表，
逐网络对比它和源 JSON 是否一致。

这是「JSON → 原理图」这一步唯一可靠的验收方式：
不看图好不好看，只看 KiCad 认为谁和谁连在一起，跟你想的是不是一样。

用法：
    python scripts/verify_sch.py out/arduino_min_system_netlist.json out/arduino_min_system.kicad_sch
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import kicad_env, sch_writer  # noqa: E402


def export_netlist(sch: Path, out: Path) -> tuple:
    cli = kicad_env.kicad_cli_path()
    if not cli:
        return False, "找不到 kicad-cli"
    try:
        proc = subprocess.run(
            [str(cli), "sch", "export", "netlist", "--output", str(out), str(sch)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    if proc.returncode != 0 or not out.exists():
        return False, (proc.stdout or "") + (proc.stderr or "")
    return True, ""


def parse_kicad_netlist(path: Path) -> dict:
    """把 KiCad 网表解析成 {网络名: {(位号, 引脚)}}。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    tree = sch_writer._parse(sch_writer._tokenize(text))
    result = {}
    for net in sch_writer._find_all(tree, "net"):
        name_node = next(
            (c for c in net if isinstance(c, list) and c and c[0] == "name"), None
        )
        if not name_node:
            continue
        name = sch_writer._unquote(name_node[1]).lstrip("/")
        nodes = set()
        for node in sch_writer._find_all(net, "node"):
            ref = pin = None
            for c in node:
                if isinstance(c, list) and c:
                    if c[0] == "ref":
                        ref = sch_writer._unquote(c[1])
                    elif c[0] == "pin":
                        pin = sch_writer._unquote(c[1])
            if ref and pin:
                nodes.add((ref, pin))
        result[name] = nodes
    return result


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description="原理图对账")
    parser.add_argument("netlist", help="源 JSON")
    parser.add_argument("sch", help="生成的 .kicad_sch")
    args = parser.parse_args()

    src = Path(args.netlist)
    sch = Path(args.sch)
    for p in (src, sch):
        if not p.exists():
            print("[FAIL] 文件不存在：%s" % p)
            return 2

    data = json.loads(src.read_text(encoding="utf-8"))
    expected = {}
    for net in data.get("nets", []):
        expected[net["name"]] = {
            (str(n["ref"]), str(n["pin"])) for n in net.get("nodes", [])
        }

    with tempfile.TemporaryDirectory() as tmp:
        net_path = Path(tmp) / "from_sch.net"
        ok, err = export_netlist(sch, net_path)
        if not ok:
            print("[FAIL] KiCad 导不出网表 —— 说明这个原理图 KiCad 打不开。")
            print("       %s" % err.strip()[:500])
            return 1
        actual = parse_kicad_netlist(net_path)

    print("=" * 68)
    print(" 原理图对账：%s" % sch.name)
    print("=" * 68)

    problems = 0
    for name in sorted(expected):
        want = expected[name]
        got = actual.get(name)
        if got is None:
            print("[FAIL] %-10s 图上根本没有这个网络" % name)
            problems += 1
            continue
        known = got & want
        extra = got - want
        missing = want - got
        tag = "OK  " if not extra and not missing else "差异"
        print(
            "[%s] %-10s 期望 %d 引脚，图上 %d 引脚"
            % (tag, name, len(want), len(got))
        )
        if missing:
            print("         图上缺：%s" % ", ".join("%s.%s" % x for x in sorted(missing)))
            problems += 1
        if extra:
            print("         图上多：%s" % ", ".join("%s.%s" % x for x in sorted(extra)))
            problems += 1

    stale = set(actual) - set(expected)
    stale = {n for n in stale if not n.startswith("unconnected-")}
    if stale:
        print("[WARN] 源数据里没有、但图上存在的网络：%s" % ", ".join(sorted(stale)))

    print("-" * 68)
    if problems:
        print("结论：%d 处不一致 —— JSON 和原理图对不上。" % problems)
        return 1
    print("结论：全部一致。KiCad 认定的连接关系和你给的 JSON 完全相同。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
