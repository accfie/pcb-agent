# -*- coding: utf-8 -*-
"""没有 API 密钥时的「人工中转」流水线。

思路：模型照用，只是通道靠人。
    脚本生成 Prompt -> 你粘到任意网页版大模型 -> 把回复存成文件 -> 脚本接着跑

这样模型是真参与的（报告里如实写"用 XX 模型的网页版分两步生成，人工复制"），
不是伪造数据，也不违规。

用法：
    python scripts/offline_run.py
    python scripts/offline_run.py "帮我设计一块 Arduino 最小系统板"
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import mvp  # noqa: E402  复用 prompt 与校验/输出逻辑
from src import llm, netlist_check, sch_writer  # noqa: E402

WORK = ROOT / "out" / "offline"


def banner(text: str) -> None:
    print()
    print("=" * 68)
    print(" " + text)
    print("=" * 68)


def ask_continue(prompt: str) -> None:
    try:
        input(prompt)
    except EOFError:
        pass


def find_reply(base: Path):
    """找回模型回复。兼容记事本存成 .json.txt 的情况。"""
    for cand in (base, base.parent / (base.name + ".txt")):
        if cand.exists():
            return cand
    return None


def read_text_smart(path: Path) -> str:
    """记事本可能存成 UTF-8 / UTF-16 / GBK，逐个试。"""
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "gbk"):
        try:
            text = raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
        if text.count("\ufffd") <= 2:
            return text
    return raw.decode("utf-8", errors="replace")


def load_reply(path: Path) -> dict:
    """读用户保存的模型回复，容忍 ```json 包裹。"""
    return llm._extract_json(read_text_smart(path))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    requirement = sys.argv[1] if len(sys.argv) > 1 else "帮我设计一块 Arduino 最小系统板"
    os.environ["PCB_AGENT_MODE"] = "manual"  # 让报告如实写"人工中转"
    WORK.mkdir(parents=True, exist_ok=True)

    print("需求：%s" % requirement)
    print("工作目录：%s" % WORK)

    # ---------------- 第一步：生成 BOM ----------------
    p1_text = WORK / "step1_prompt.txt"
    p1_text.write_text(
        "%s\n\n需求：%s" % (mvp.BOM_SYSTEM, requirement), encoding="utf-8"
    )
    r1 = WORK / "step1_reply.json"

    banner("第 1 步 / 共 2 步：让模型产出 BOM")
    print("Prompt 已写入：%s" % p1_text)
    print()
    print("要做的三件事：")
    print("  1. 打开这个 txt，全选复制")
    print("  2. 粘到任意网页版大模型（山大 AI 助手 / DeepSeek / 通义 / Kimi 都行）")
    print("  3. 把模型的完整回复存成：%s" % r1)
    print()
    print("  （记事本存成 .json 时，编码选 UTF-8；回复里的 ```json 标记不用删，脚本会自己剥掉）")

    if not find_reply(r1):
        ask_continue("存好后按回车继续……")
    r1_real = find_reply(r1)
    if not r1_real:
        print("[FAIL] 没找到 %s，先把它存好再重跑。" % r1.name)
        print("       提示：用记事本保存时，把文件名连引号一起输入 \"%s\"" % r1.name)
        print("       或者在「保存类型」里选「所有文件」，否则会变成 %s.txt（这个也能用）" % r1.name)
        return 1

    try:
        bom = load_reply(r1_real)
    except Exception as exc:  # noqa: BLE001
        print("[FAIL] 回复不是合法 JSON：%s" % exc)
        print("       把模型的原回复整段存进来，别手工改。")
        return 1

    comps = bom.get("components") or []
    if not comps:
        print("[FAIL] 回复里没有 components 数组，模型可能没按要求输出。")
        return 1
    print("[ OK ] 读到 %d 个器件" % len(comps))

    # ---------------- 第二步：生成连接关系 ----------------
    p2_text = WORK / "step2_prompt.txt"
    p2_text.write_text(
        "%s\n\nBOM 如下：\n%s"
        % (mvp.NET_SYSTEM, json.dumps(bom, ensure_ascii=False, indent=2)),
        encoding="utf-8",
    )
    r2 = WORK / "step2_reply.json"

    banner("第 2 步 / 共 2 步：让模型展开成引脚级连接")
    print("Prompt 已写入：%s" % p2_text)
    print()
    print("同样三步：复制 → 粘到模型 → 回复存成 %s" % r2)

    if not find_reply(r2):
        ask_continue("存好后按回车继续……")
    r2_real = find_reply(r2)
    if not r2_real:
        print("[FAIL] 没找到 %s。" % r2.name)
        return 1

    try:
        netlist = load_reply(r2_real)
    except Exception as exc:  # noqa: BLE001
        print("[FAIL] 回复不是合法 JSON：%s" % exc)
        return 1

    # ---------------- 校验 + 出文件 ----------------
    banner("校验结构")
    errors, warnings = netlist_check.validate(netlist)
    for w in warnings[:10]:
        print("[WARN] %s" % w)
    for e in errors[:10]:
        print("[FAIL] %s" % e)

    result = {"netlist": netlist, "errors": errors, "warnings": warnings}
    paths = mvp.write_outputs(WORK, requirement, bom, result)

    print()
    print("产物：")
    for label, p in paths.items():
        print("  %-8s %s" % (label, p))

    if errors:
        print()
        print("结构有问题，但照样能试着出图。把上面 [FAIL] 的内容复制给模型，让它修一版重存。")
    else:
        print()
        print("[ OK ] 结构校验通过（0 错误，%d 警告）" % len(warnings))

    # ---------------- 顺手生成原理图 ----------------
    banner("生成 KiCad 原理图")
    sch_path = WORK / ("%s.kicad_sch" % (netlist.get("board", {}).get("name", "board")))
    try:
        ws = sch_writer.netlist_to_file(netlist, sch_path, project_name="pcb-agent")
        for w in ws:
            print("[WARN] %s" % w)
        print("[ OK ] %s" % sch_path)
        print()
        print("自动对账：让 KiCad 把原理图反导成网表，再跟你给的连接关系逐条比。")
        print()
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "verify_sch.py"),
                str(paths["net"]),
                str(sch_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
        )
        if proc.stdout:
            print(proc.stdout.rstrip())
        if proc.returncode != 0 and proc.stderr:
            print(proc.stderr.rstrip())
    except Exception as exc:  # noqa: BLE001
        print("[WARN] 原理图没生成：%s" % exc)

    print()
    print("=" * 68)
    print(" 完成。要写进报告的话：")
    print(" 本方案使用 XX 大模型网页版，分「生成 BOM」「展开连接」两步交互完成，")
    print(" 由人工复制粘贴中转，脚本负责结构校验、JSON→原理图转换与网表对账。")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
