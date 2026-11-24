# -*- coding: utf-8 -*-
"""全自动流水线：一句话 -> BOM -> 连接关系 -> 原理图 -> PDF -> 对账。

不需要人工复制粘贴，前提是 .env 里配好了一个**程序能直接调用**的模型接口：
    - 课程/自购的 API 密钥（OpenAI 兼容）
    - 或者本机 Ollama（http://localhost:11434/v1）

用法：
    python scripts/auto_run.py "帮我设计一块 Arduino 最小系统板"
    python scripts/auto_run.py --check          # 只检查接口是否通
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import mvp  # noqa: E402
from src import kicad_env, llm, netlist_check, sch_writer, settings  # noqa: E402

OUT = ROOT / "out" / "auto"


def check_endpoint() -> bool:
    """发一条最短请求，确认接口和模型名都对。"""
    print("检查模型接口 ……")
    print("  BASE_URL : %s" % settings.llm_base_url())
    print("  MODEL    : %s" % settings.llm_model())
    key = settings.llm_api_key()
    print("  API_KEY  : %s" % ("已填写" if not settings.is_placeholder(key) else "未填写"))
    print()
    try:
        data = llm.chat_json(
            "你是一个测试助手。只输出 JSON。",
            '输出 {"ok": true}',
            max_retries=0,
        )
        print("[ OK ] 接口连通，模型返回：%s" % str(data)[:80])
        return True
    except Exception as exc:  # noqa: BLE001
        print("[FAIL] %s" % exc)
        print()
        print("常见原因：")
        print("  1. LLM_API_KEY 没填或填错")
        print("  2. LLM_MODEL 名字不对（比如 qwen-max 写成 qwen）")
        print("  3. 用的是本地 Ollama 但没启动：先运行 ollama serve")
        return False


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description="全自动：一句话到原理图")
    parser.add_argument("requirement", nargs="?", default="帮我设计一块 Arduino 最小系统板")
    parser.add_argument("--check", action="store_true", help="只检查模型接口")
    args = parser.parse_args()

    if args.check:
        return 0 if check_endpoint() else 1

    print("=" * 68)
    print(" 全自动模式")
    print(" 需求：%s" % args.requirement)
    print(" 模型：%s @ %s" % (settings.llm_model(), settings.llm_base_url()))
    print("=" * 68)
    print()

    if settings.is_placeholder(settings.llm_api_key()):
        print("[FAIL] 没有配置 LLM_API_KEY，无法全自动。")
        print("       要么填密钥，要么改用本机 Ollama（见 docs/auto-mode.md）。")
        return 1

    # 1-3：BOM -> 连接关系 -> 校验（不合格会自动回喂重试）
    try:
        bom = mvp.step_bom(args.requirement, False)
        netlist = mvp.step_netlist(bom, False)
        fixes = netlist_check.repair(netlist)
        if fixes:
            print()
            print("自动修复（每处都写明，不偷偷改）：")
            for f in fixes:
                print("  " + f)
            print()
        print("[3/5] 校验结构 ……")
        result = mvp.step_validate(netlist, bom, False, args.requirement)
        # 校验失败时会重试并返回新对象，后续必须用这一份，否则改的和写出去的不是同一份
        netlist = result["netlist"]
    except llm.LLMError as exc:
        print("[FAIL] %s" % exc)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)

    # 符号名纠错：模型常把芯片型号当符号名，先修好再落盘
    print()
    fixes = sch_writer.fix_symbols(netlist)
    if fixes:
        print("符号检查：")
        for f in fixes:
            print("  " + f)
    else:
        print("符号检查：全部命中 KiCad 库")

    paths = mvp.write_outputs(OUT, args.requirement, bom, result)

    if result["errors"]:
        print()
        print("[WARN] 结构有 %d 个错误，仍然继续出图，但建议检查。" % len(result["errors"]))

    # 4：原理图 + PDF
    print()
    print("[4/5] 生成原理图 ……")
    board = (netlist.get("board") or {}).get("name", "board")
    sch_path = OUT / ("%s.kicad_sch" % board)
    try:
        warnings = sch_writer.netlist_to_file(netlist, sch_path, project_name="pcb-agent")
        for w in warnings:
            print("  [WARN] %s" % w)
        print("  [ OK ] %s" % sch_path.name)
    except Exception as exc:  # noqa: BLE001
        print("  [FAIL] %s" % exc)
        return 1

    cli = kicad_env.kicad_cli_path()
    if cli:
        pdf = OUT / ("%s.pdf" % board)
        subprocess.run(
            [str(cli), "sch", "export", "pdf", "--output", str(pdf), str(sch_path)],
            capture_output=True,
        )
        if pdf.exists():
            print("  [ OK ] %s" % pdf.name)

    # 5：对账
    print()
    print("[5/5] 对账 ……")
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

    print()
    print("=" * 68)
    print(" 产物目录：%s" % OUT)
    print("=" * 68)
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
