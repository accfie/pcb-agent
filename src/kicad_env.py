# -*- coding: utf-8 -*-
"""KiCad 环境探测。

Windows 上 KiCad 自带一个独立的 Python 解释器（8.x 通常是 3.11），
`pcbnew` 这类模块只有用它才能 import。本模块负责把这些路径找出来，
避免每个脚本各写一遍。
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

# 常见的 KiCad 安装根目录。按顺序探测，找到第一个含版本子目录的即为候选。
CANDIDATE_ROOTS = [
    r"C:\Program Files\KiCad",
    r"C:\Program Files (x86)\KiCad",
    r"D:\Program Files\KiCad",
    r"D:\KiCad",
    r"E:\KiCad",
]


def _version_key(name: str) -> tuple:
    parts = []
    for p in name.replace("-", ".").split("."):
        parts.append(int(p) if p.isdigit() else -1)
    return tuple(parts)


def _from_registry() -> Optional[Path]:
    """从 Windows 卸载表里读 KiCad 的安装位置。

    用户安装时可以改路径（本例就在 D:\\apps\\KiCad），硬编码路径靠不住，
    注册表才是唯一可靠的来源。
    """
    try:
        import winreg  # type: ignore
    except ImportError:
        return None

    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    found = []
    for hive, sub in roots:
        try:
            with winreg.OpenKey(hive, sub) as key:
                count = winreg.QueryInfoKey(key)[0]
                for i in range(count):
                    try:
                        name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, name) as entry:
                            try:
                                display = winreg.QueryValueEx(entry, "DisplayName")[0]
                            except OSError:
                                continue
                            if not str(display).lower().startswith("kicad"):
                                continue
                            try:
                                loc = winreg.QueryValueEx(entry, "InstallLocation")[0]
                            except OSError:
                                continue
                            if loc and (Path(loc) / "bin" / "kicad-cli.exe").exists():
                                found.append(Path(loc))
                    except OSError:
                        continue
        except OSError:
            continue

    if not found:
        return None
    # 装了多个版本时取版本号最大的
    return sorted(found, key=lambda p: _version_key(p.parent.name or p.name))[-1]


def find_kicad_root() -> Optional[Path]:
    """返回 KiCad 安装根目录（含版本号的那一层），找不到返回 None。"""
    env_home = os.environ.get("KICAD_HOME", "").strip()
    roots = ([env_home] if env_home else []) + CANDIDATE_ROOTS

    for root in roots:
        base = Path(root)
        if not base.is_dir():
            continue
        # 情况一：root 本身就是版本目录（用户直接把 KICAD_HOME 指到 8.0）
        if (base / "bin" / "kicad-cli.exe").exists():
            return base
        # 情况二：root 下挂着 8.0 / 9.0 这样的版本目录，取最高版本
        subs = [d for d in base.iterdir() if d.is_dir() and (d / "bin").is_dir()]
        subs = [d for d in subs if (d / "bin" / "kicad-cli.exe").exists()]
        if subs:
            return sorted(subs, key=lambda d: _version_key(d.name))[-1]

    return _from_registry()


def kicad_cli_path() -> Optional[Path]:
    which = shutil.which("kicad-cli")
    if which:
        return Path(which)
    root = find_kicad_root()
    if root:
        candidate = root / "bin" / "kicad-cli.exe"
        if candidate.exists():
            return candidate
    return None


def bundled_python() -> Optional[Path]:
    """KiCad 自带的 python.exe；没有 python.exe 时退回到 pythonw 以外的东西。"""
    root = find_kicad_root()
    if not root:
        return None
    for name in ("python.exe", "python3.exe"):
        candidate = root / "bin" / name
        if candidate.exists():
            return candidate
    return None


def run(cmd: list, timeout: int = 30) -> tuple:
    """跑个子进程，返回 (returncode, stdout+stderr)。失败不抛异常。"""
    try:
        proc = subprocess.run(
            [str(c) for c in cmd],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()
    except FileNotFoundError:
        return -1, "找不到可执行文件: %s" % cmd[0]
    except subprocess.TimeoutExpired:
        return -2, "执行超时（%ss）" % timeout
    except Exception as exc:  # noqa: BLE001 - 探测脚本不该因为环境怪而崩
        return -3, "执行异常: %s" % exc


def kicad_cli_version() -> Optional[str]:
    cli = kicad_cli_path()
    if not cli:
        return None
    code, out = run([cli, "--version"])
    if code != 0:
        return None
    return out.splitlines()[0].strip() if out else None


def pcbnew_version(python_exe: Optional[Path] = None) -> Optional[str]:
    """用指定解释器 import pcbnew 并取版本；失败返回 None。"""
    exe = python_exe or bundled_python()
    if not exe:
        return None
    code, out = run([exe, "-c", "import pcbnew; print(pcbnew.Version())"])
    if code != 0:
        return None
    return out.splitlines()[-1].strip() if out else None


def has_eeschema_api() -> bool:
    """KiCad 8 没有官方 eeschema Python API。

    原理图要么直接生成 .kicad_sch（S-expression 文本），
    要么借助 kicad-skip 这类第三方库。这里只做提示，不做探测。
    """
    return False
