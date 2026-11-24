# -*- coding: utf-8 -*-
"""第 5 步：交互修正。改一句话，重新生成原理图。

对应课程要求：「支持用户追问改需求（如『把电容换成 100nF』）并重新生成」

用法：
    python scripts/revise.py "把 C1 和 C2 换成 18pF"
    python scripts/revise.py "删除 C5"
    python scripts/revise.py --net out/offline/xxx.json "把 R2 换成 470"

做的事：解析这句话 -> 改连接关系 JSON -> 重新生成原理图/PDF -> 自动对账
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import kicad_env, netlist_check, sch_writer  # noqa: E402

DEFAULT_NET = ROOT / "out" / "offline" / "arduino_min_system_netlist.json"

REF_RE = re.compile(r"\b(SW\d+|[RCUYDJ]\d+)\b", re.I)
VALUE_RE = re.compile(
    r"(?:换|改)成?\s*([0-9]+(?:\.[0-9]+)?\s*[a-zA-ZµμΩ]*)", re.I
)
DROP_RE = re.compile(r"(删除|去掉|移除|不要)\s*(?:器件|元件)?\s*", re.I)


def parse_instruction(text: str) -> tuple:
    """把一句话解析成 (操作列表, 错误说明)。操作形如 ('set', 'C1', '18pF') / ('drop','C5',None)。"""
    ops = []
    refs = [r.upper() for r in REF_RE.findall(text)]
    if not refs:
        return [], "没听懂要改哪个器件。请写成「把 C1 换成 18pF」或「删除 C5」。"

    is_drop = bool(DROP_RE.search(text))
    if is_drop:
        for r in refs:
            ops.append(("drop", r, None))
        return ops, ""

    m = VALUE_RE.search(text)
    if not m:
        return [], "找到了器件 %s，但没听懂要改成什么值。请写成「把 %s 换成 18pF」。" % (
            "、".join(refs),
            refs[0],
        )
    value = re.sub(r"\s+", "", m.group(1))
    for r in refs:
        ops.append(("set", r, value))
    return ops, ""


def apply_ops(netlist: dict, ops: list) -> tuple:
    """返回 (新的 netlist, 变更说明列表)。"""
    data = json.loads(json.dumps(netlist))  # 深拷贝
    changes = []
    by_ref = {c["ref"].upper(): c for c in data["components"]}

    for kind, ref, value in ops:
        comp = by_ref.get(ref)
        if not comp:
            changes.append("[跳过] %s 不在这块板上" % ref)
            continue

        if kind == "set":
            old = comp.get("value", "")
            if old == value:
                changes.append("[不变] %s 本来就是 %s" % (ref, value))
                continue
            comp["value"] = value
            changes.append("[改值] %s：%s -> %s" % (ref, old, value))
        elif kind == "drop":
            data["components"] = [c for c in data["components"] if c["ref"].upper() != ref]
            for net in data["nets"]:
                before = len(net["nodes"])
                net["nodes"] = [
                    n for n in net["nodes"] if str(n["ref"]).upper() != ref
                ]
                if len(net["nodes"]) != before:
                    changes.append(
                        "[断线] 网络 %s 移除了 %s 的引脚（剩 %d 个）"
                        % (net["name"], ref, len(net["nodes"]))
                    )
            data["nets"] = [n for n in data["nets"] if len(n["nodes"]) >= 2]
            changes.append("[删件] %s 已从 BOM 和连接关系中移除" % ref)

    return data, changes


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description="一句话修改设计并重新生成原理图")
    parser.add_argument("instruction", nargs="?", default="", help="修改要求，例如：把 C1 和 C2 换成 18pF")
    parser.add_argument("--net", default=str(DEFAULT_NET), help="要修改的连接关系 JSON")
    parser.add_argument(
        "-i", "--interactive", action="store_true", help="交互式：先问你要改什么"
    )
    args = parser.parse_args()

    instruction = args.instruction
    if args.interactive or not instruction:
        print()
        print("可以这样说：")
        print("  把 C1 和 C2 换成 18pF")
        print("  把 R2 换成 470")
        print("  删除 C5")
        print()
        try:
            instruction = input("  你的修改要求：").strip()
        except EOFError:
            instruction = ""
        if not instruction:
            print("  没输入内容，已跳过。")
            return 0

    src = Path(args.net)
    if not src.exists():
        print("[FAIL] 找不到 %s —— 先跑一次 一键运行.bat 生成它。" % src)
        return 2

    print()
    print("=" * 68)
    print(" 修改要求：%s" % instruction)
    print("=" * 68)

    ops, err = parse_instruction(instruction)
    if err:
        print("[FAIL] %s" % err)
        return 1
    print("解析结果：%s" % ", ".join("%s %s%s" % (k, r, "=" + v if v else "") for k, r, v in ops))
    print()

    netlist = json.loads(src.read_text(encoding="utf-8"))
    revised, changes = apply_ops(netlist, ops)
    for c in changes:
        print("  " + c)

    errors, warnings = netlist_check.validate(revised)
    print()
    if errors:
        print("改完后结构有问题：")
        for e in errors[:6]:
            print("  [FAIL] %s" % e)
        print("  继续出图，但请检查上面的问题。")
    else:
        print("[ OK ] 改完后结构依然合法（%d 个警告）" % len(warnings))

    out_dir = src.parent
    board = (revised.get("board") or {}).get("name", "board")
    net_path = out_dir / ("%s_revised.json" % board)
    net_path.write_text(
        json.dumps(revised, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    sch_path = out_dir / ("%s_revised.kicad_sch" % board)
    print()
    print("重新生成原理图 ……")
    try:
        ws = sch_writer.netlist_to_file(revised, sch_path, project_name="pcb-agent")
        for w in ws:
            print("  [WARN] %s" % w)
        print("  [ OK ] %s" % sch_path.name)
    except Exception as exc:  # noqa: BLE001
        print("  [FAIL] %s" % exc)
        return 1

    # PDF
    cli = kicad_env.kicad_cli_path()
    if cli:
        pdf_path = out_dir / ("%s_revised.pdf" % board)
        subprocess.run(
            [str(cli), "sch", "export", "pdf", "--output", str(pdf_path), str(sch_path)],
            capture_output=True,
        )
        if pdf_path.exists():
            print("  [ OK ] %s" % pdf_path.name)

    # 自动对账
    print()
    print("自动对账 ……")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_sch.py"), str(net_path), str(sch_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
    )
    if proc.stdout:
        print(proc.stdout.rstrip())

    print()
    print("产物：%s / %s" % (net_path.name, sch_path.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
