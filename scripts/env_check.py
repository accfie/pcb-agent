# -*- coding: utf-8 -*-
"""第一周环境自检。

用法（在项目根目录执行）：
    python scripts/env_check.py

它会逐项检查：Python 版本、依赖包、.env 配置、KiCad 安装、
KiCad 自带 Python、课程模板工程、Git 仓库。
有阻断项不通过时退出码为 1，方便以后接进 CI。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import kicad_env, settings  # noqa: E402

OK = "[ OK ]"
FAIL = "[FAIL]"
WARN = "[WARN]"
INFO = "[INFO]"

results = []  # (status, title, detail)


def add(status: str, title: str, detail: str = "") -> None:
    results.append((status, title, detail))


MIN_PY = (3, 10)


def check_python() -> None:
    ver = sys.version_info
    version_text = "%d.%d.%d" % (ver.major, ver.minor, ver.micro)
    if (ver.major, ver.minor) >= MIN_PY:
        add(OK, "Python 版本", "%s  (要求 >= 3.10)" % version_text)
    else:
        add(FAIL, "Python 版本", "%s 过低，需要 >= 3.10" % version_text)
    add(INFO, "解释器路径", sys.executable)


def check_packages() -> None:
    required = {
        "dotenv": "python-dotenv",
        "openai": "openai",
        "requests": "requests",
    }
    for module, package in required.items():
        spec = importlib.util.find_spec(module)
        if spec:
            add(OK, "依赖包 %s" % package, "已安装")
        else:
            add(WARN, "依赖包 %s" % package, "未安装 → pip install -r requirements.txt")


def check_env_file() -> None:
    if not settings.ENV_FILE.exists():
        add(FAIL, ".env 配置文件", "不存在 → 复制 .env.example 为 .env 并填写")
        return
    add(OK, ".env 配置文件", str(settings.ENV_FILE))

    key = settings.llm_api_key()
    if settings.is_placeholder(key):
        add(FAIL, "LLM_API_KEY", "未填写 → 去课程群领取密钥后填入 .env")
    else:
        add(OK, "LLM_API_KEY", "已填写（%s...，共 %d 位）" % (key[:6], len(key)))

    add(INFO, "LLM_BASE_URL", settings.llm_base_url())
    add(INFO, "LLM_MODEL", settings.llm_model())


def check_kicad_version(cli_version: str) -> None:
    """课程模板基于 KiCad 8，主版本不一致会导致提交物打不开。"""
    import re

    match = re.match(r"(\d+)\.", cli_version.strip())
    if not match:
        return
    major = int(match.group(1))
    if major == 8:
        add(OK, "KiCad 版本匹配", "8.x，与课程模板一致")
    else:
        add(
            WARN,
            "KiCad 版本不匹配",
            "检测到 %d.x，课程要求 8.x —— %d 保存的 .kicad_sch 在 KiCad 8 里打不开。"
            "提交物请用 8.0.8 生成，或先跟助教确认是否允许新版本" % (major, major),
        )


def check_kicad() -> None:
    root = kicad_env.find_kicad_root()
    if not root:
        add(
            FAIL,
            "KiCad 安装",
            "未找到 → 安装 KiCad 8.0.8（https://mirrors.aliyun.com/kicad/windows/"
            "stable/kicad-8.0.8-x86_64.exe），"
            "装完若仍在非默认盘，请在 .env 里设置 KICAD_HOME",
        )
        return

    add(OK, "KiCad 安装目录", str(root))

    cli_version = kicad_env.kicad_cli_version()
    if cli_version:
        add(OK, "kicad-cli", cli_version)
        check_kicad_version(cli_version)
    else:
        add(WARN, "kicad-cli", "存在但执行失败，检查 %s" % (root / "bin" / "kicad-cli.exe"))

    py = kicad_env.bundled_python()
    if py:
        add(OK, "KiCad 自带 Python", str(py))
        ver = kicad_env.pcbnew_version(py)
        if ver:
            add(OK, "pcbnew 模块", "版本 %s" % ver)
        else:
            add(WARN, "pcbnew 模块", "import 失败，PCB 脚本能力可能不可用")
    else:
        add(WARN, "KiCad 自带 Python", "未找到 bin/python.exe，PCB 脚本接口不可用")

    add(
        INFO,
        "原理图脚本接口",
        "KiCad 8 没有官方 eeschema Python API，生成原理图靠直接写 .kicad_sch 文本"
        "（或 kicad-skip 等第三方库）",
    )


def check_template() -> None:
    tpl = settings.template_dir()
    if not tpl:
        add(
            FAIL,
            "课程模板工程",
            "未配置 → 从课程群下载模板，解压后把绝对路径填进 .env 的 TEMPLATE_DIR",
        )
        return
    if not tpl.exists():
        add(FAIL, "课程模板工程", "路径不存在：%s" % tpl)
        return

    pro_files = sorted(tpl.glob("*.kicad_pro"))
    if pro_files:
        add(OK, "课程模板工程", "%s  （找到 %s）" % (tpl, pro_files[0].name))
    else:
        add(WARN, "课程模板工程", "%s 存在，但没找到 .kicad_pro，确认是不是解压到了子目录" % tpl)


def check_git() -> None:
    if (ROOT / ".git").exists():
        add(OK, "Git 仓库", "已初始化")
    else:
        add(WARN, "Git 仓库", "未初始化 → git init，过程分靠 commit 记录")

    import subprocess

    name = subprocess.run(
        ["git", "config", "user.name"], capture_output=True, text=True
    ).stdout.strip()
    email = subprocess.run(
        ["git", "config", "user.email"], capture_output=True, text=True
    ).stdout.strip()
    if name and email:
        add(OK, "Git 身份", "%s <%s>" % (name, email))
    else:
        add(
            WARN,
            "Git 身份",
            '未配置 → git config --global user.name "你的名字"；'
            'git config --global user.email "你的邮箱"',
        )


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    print("=" * 68)
    print(" AI Agent 电路板设计 · 第一周环境自检")
    print("=" * 68)

    check_python()
    check_packages()
    check_env_file()
    check_kicad()
    check_template()
    check_git()

    print()
    for status, title, detail in results:
        print("%s %-22s %s" % (status, title, detail))

    failed = sum(1 for r in results if r[0] == FAIL)
    warned = sum(1 for r in results if r[0] == WARN)

    print()
    print("-" * 68)
    if failed:
        print("结论：%d 项阻断、%d 项警告 —— 先把 [FAIL] 全部消掉。" % (failed, warned))
        print("第一周里程碑「脚手架跑通」尚未达成。")
        return 1
    print("结论：0 项阻断、%d 项警告。" % warned)
    if warned:
        print("警告不影响继续，但建议一并处理。")
    print("第一周里程碑「脚手架跑通」已达成，可以开始 W2 的 Prompt 设计。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
