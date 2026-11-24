# -*- coding: utf-8 -*-
"""最小闭环 MVP：一句话需求 -> BOM -> 连接关系 JSON -> 校验 -> 产出文件。

这是基础任务的第 2、3 步。先用 --mock 把链路跑通，密钥到位后去掉 --mock
就是真实调用。

用法：
    python scripts/mvp.py --mock
    python scripts/mvp.py "帮我设计一块 Arduino 最小系统板"
    python scripts/mvp.py "设计一块 STM32F103 最小系统板" --out out/stm32
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import llm, netlist_check  # noqa: E402

BOM_SYSTEM = """你是资深硬件工程师，负责把自然语言需求转成元器件清单（BOM）。
只输出 JSON，不要解释。结构：
{"board": {"name": "英文短名", "description": "一句话说明", "mcu": "主控型号"},
 "components": [
   {"ref": "U1", "value": "型号/参数", "quantity": 1, "footprint": "KiCad 封装名", "purpose": "这个器件干什么"}
 ]}
规则：
- 位号前缀按器件类型：U 芯片、R 电阻、C 电容、Y 晶振、D 二极管、SW 开关、J 接插件
- footprint 必须是 KiCad 官方库里的真实名字，例如 Package_DIP:DIP-28_W7.62mm
- 只列必要器件，不要堆砌"""

NET_SYSTEM = """你是资深硬件工程师，要把 BOM 展开成引脚级连接关系。
只输出 JSON，不要解释。结构：
{"schema_version": "0.1",
 "board": {"name": "...", "description": "...", "mcu": "..."},
 "components": [
   {"ref": "U1", "value": "...", "symbol": "库里名:符号名", "footprint": "封装名",
    "pins": {"引脚号": "引脚名"}}
 ],
 "nets": [
   {"name": "网络名", "nodes": [{"ref": "U1", "pin": "7"}]}
 ]}
规则：
- pins 的键必须是引脚**编号**（字符串），值是该脚的功能名
- 每个网络至少连 2 个引脚；单独一端的引脚不要建网络
- 必须有 VCC 和 GND 两个网络
- 网络名用大写英文：VCC / GND / RESET / XTAL1 / XTAL2 / 自定义信号名
- 不要编造 BOM 里不存在的位号"""


def mock_bom() -> dict:
    data = llm.load_mock_netlist()
    comps = []
    for c in data["components"]:
        comps.append(
            {
                "ref": c["ref"],
                "value": c["value"],
                "quantity": 1,
                "footprint": c["footprint"],
                "purpose": "（mock 数据，未生成说明）",
            }
        )
    return {"board": data["board"], "components": comps}


def step_bom(requirement: str, mock: bool) -> dict:
    if mock:
        print("[1/3] 生成 BOM …… mock 模式，读取本地样例")
        return mock_bom()
    print("[1/3] 生成 BOM …… 调用模型")
    return llm.chat_json(BOM_SYSTEM, "需求：%s" % requirement)


def step_netlist(bom: dict, mock: bool) -> dict:
    if mock:
        print("[2/3] 生成连接关系 …… mock 模式，读取本地样例")
        return llm.load_mock_netlist()
    print("[2/3] 生成连接关系 …… 调用模型")
    return llm.chat_json(NET_SYSTEM, "BOM 如下：\n%s" % json.dumps(bom, ensure_ascii=False))


def step_validate(netlist: dict, bom: dict, mock: bool, requirement: str) -> dict:
    """校验；不合法就把错误回喂给模型重生成一次（反馈闭环）。"""
    errors, warnings = netlist_check.validate(netlist)
    if not errors:
        return {"netlist": netlist, "errors": [], "warnings": warnings}

    print("      校验失败 %d 项，回喂给模型重试一次" % len(errors))
    for e in errors[:5]:
        print("        - %s" % e)
    if mock:
        return {"netlist": netlist, "errors": errors, "warnings": warnings}

    retry = llm.chat_json(
        NET_SYSTEM,
        "原需求：%s\nBOM：%s\n\n你上一版输出有这些错误，请修正后重新输出完整 JSON：\n%s"
        % (
            requirement,
            json.dumps(bom, ensure_ascii=False),
            "\n".join("- " + e for e in errors),
        ),
    )
    errors2, warnings2 = netlist_check.validate(retry)
    if not errors2:
        print("      重试成功")
        return {"netlist": retry, "errors": [], "warnings": warnings2}
    return {"netlist": retry, "errors": errors2, "warnings": warnings2}


def write_outputs(out_dir: Path, requirement: str, bom: dict, result: dict) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    board = (result["netlist"].get("board") or {}).get("name", "board")

    bom_path = out_dir / ("%s_bom.csv" % board)
    with bom_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["ref", "value", "footprint", "quantity", "purpose"])
        for c in bom.get("components", []):
            writer.writerow(
                [
                    c.get("ref", ""),
                    c.get("value", ""),
                    c.get("footprint", ""),
                    c.get("quantity", 1),
                    c.get("purpose", ""),
                ]
            )

    net_path = out_dir / ("%s_netlist.json" % board)
    net_path.write_text(
        json.dumps(result["netlist"], ensure_ascii=False, indent=2), encoding="utf-8"
    )

    report_path = out_dir / ("%s_report.md" % board)
    report_path.write_text(
        build_report(requirement, bom, result), encoding="utf-8"
    )

    return {"bom": bom_path, "net": net_path, "report": report_path}


def build_report(requirement: str, bom: dict, result: dict) -> str:
    net = result["netlist"]
    board = net.get("board") or {}
    mode = llm.mode_label()

    lines = [
        "# %s" % board.get("name", "board"),
        "",
        "- 需求原文：%s" % requirement,
        "- 说明：%s" % board.get("description", ""),
        "- 主控：%s" % board.get("mcu", ""),
        "- 生成方式：%s" % mode,
        "- 生成时间：%s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "",
        "## 元器件清单（BOM）",
        "",
        "| 位号 | 型号/参数 | 封装 | 数量 | 用途 |",
        "|---|---|---|---|---|",
    ]
    for c in bom.get("components", []):
        lines.append(
            "| %s | %s | %s | %s | %s |"
            % (
                c.get("ref", ""),
                c.get("value", ""),
                c.get("footprint", ""),
                c.get("quantity", 1),
                c.get("purpose", ""),
            )
        )

    lines += ["", "## 网络连接关系", "", "| 网络 | 连接引脚 |", "|---|---|"]
    for n in net.get("nets", []):
        nodes = ", ".join(
            "%s.%s" % (x.get("ref", "?"), x.get("pin", "?")) for x in n.get("nodes", [])
        )
        lines.append("| %s | %s |" % (n.get("name", "?"), nodes))

    lines += ["", "## 结构校验", ""]
    if result["errors"]:
        lines.append("**未通过**，共 %d 项错误：" % len(result["errors"]))
        lines += ["- %s" % e for e in result["errors"]]
    else:
        lines.append("通过，0 项错误。")
    if result["warnings"]:
        lines += ["", "警告 %d 项：" % len(result["warnings"])]
        lines += ["- %s" % w for w in result["warnings"]]
    return "\n".join(lines) + "\n"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description="一句话需求 -> BOM + 连接关系")
    parser.add_argument("requirement", nargs="?", default="帮我设计一块 Arduino 最小系统板")
    parser.add_argument("--mock", action="store_true", help="不调用模型，用本地样例跑通链路")
    parser.add_argument("--out", default="out", help="产物输出目录")
    args = parser.parse_args()

    if args.mock:
        import os

        os.environ[llm.MOCK_ENV] = "1"

    print("=" * 68)
    print(" 需求：%s" % args.requirement)
    print(" 模式：%s" % ("mock" if args.mock else "真实模型"))
    print("=" * 68)

    try:
        bom = step_bom(args.requirement, args.mock)
        netlist = step_netlist(bom, args.mock)
        print("[3/3] 校验结构 ……")
        result = step_validate(netlist, bom, args.mock, args.requirement)
    except llm.LLMError as exc:
        print("[FAIL] %s" % exc)
        print("       想先看链路效果，加 --mock 参数。")
        return 1

    paths = write_outputs(Path(args.out), args.requirement, bom, result)

    print()
    print("器件 %d 个，网络 %d 个"
          % (len(bom.get("components", [])), len(result["netlist"].get("nets", []))))
    if result["errors"]:
        print("校验：未通过（%d 项错误）" % len(result["errors"]))
    else:
        print("校验：通过（%d 项警告）" % len(result["warnings"]))
    print()
    for label, p in paths.items():
        print("  %-8s %s" % (label, p))
    print()
    print("下一步：把 %s 变成 .kicad_sch（W5–W6 的事）" % paths["net"].name)
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
