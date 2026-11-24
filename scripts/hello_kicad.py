# -*- coding: utf-8 -*-
"""验证 KiCad 脚本接口真的能用。

做两件事：
  1. 报告 kicad-cli 与 pcbnew 的版本；
  2. 用 pcbnew 建一块空板并保存到 out/_smoke.kicad_pcb —— 能生成文件
     就说明「Python 驱动 KiCad」这条路是通的。

用法（在项目根目录执行）：
    python scripts/hello_kicad.py

如果当前解释器 import 不到 pcbnew，脚本会自动改用 KiCad 自带的
python.exe 重新执行自己。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import kicad_env  # noqa: E402


def _relaunch_with_kicad_python() -> int:
    py = kicad_env.bundled_python()
    if not py:
        print("[FAIL] 当前 Python 里没有 pcbnew，也没找到 KiCad 自带的 python.exe。")
        print("       先把 KiCad 装上，或检查 .env 里的 KICAD_HOME。")
        return 1
    print("[INFO] 当前解释器没有 pcbnew，改用 KiCad 自带 Python 重新执行：")
    print("       %s" % py)
    proc = subprocess.run([str(py), str(Path(__file__).resolve())] + sys.argv[1:])
    return proc.returncode


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    print("=" * 68)
    print(" KiCad 接口连通性测试")
    print("=" * 68)

    try:
        import pcbnew  # type: ignore
    except ImportError:
        return _relaunch_with_kicad_python()

    print("[ OK ] pcbnew 版本：%s" % pcbnew.Version())

    cli = kicad_env.kicad_cli_path()
    if cli:
        code, out = kicad_env.run([cli, "--version"])
        print("[ OK ] kicad-cli：%s" % (out.splitlines()[0] if out else "已找到"))
    else:
        print("[WARN] 没找到 kicad-cli，命令行导出能力不可用")

    # 建一块空板，证明写文件的能力是通的
    out_dir = ROOT / "out"
    out_dir.mkdir(exist_ok=True)
    target = out_dir / "_smoke.kicad_pcb"

    board = pcbnew.CreateEmptyBoard() if hasattr(pcbnew, "CreateEmptyBoard") else pcbnew.BOARD()
    pcbnew.SaveBoard(str(target), board)

    if target.exists():
        size = target.stat().st_size
        print("[ OK ] 已生成空板：%s（%d 字节）" % (target.name, size))
        print()
        print("结论：Python → KiCad 的写入通路正常。W5–W6 的「JSON 变原理图」")
        print("      可以正式起步了。")
        return 0

    print("[FAIL] 空板文件没有生成，检查 out/ 目录权限。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
