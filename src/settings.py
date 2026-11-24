# -*- coding: utf-8 -*-
"""读取 .env 配置。

优先用 python-dotenv；没装也能跑（走内置的极简解析），
这样在装依赖之前就能执行环境自检。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"


def _parse_env_file(path: Path) -> dict:
    data = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            data[key] = value
    return data


def _load() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(ENV_FILE, override=False)
        return
    except ImportError:
        pass
    for key, value in _parse_env_file(ENV_FILE).items():
        os.environ.setdefault(key, value)


_load()


def get(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def llm_api_key() -> str:
    return get("LLM_API_KEY")


def llm_base_url() -> str:
    return get("LLM_BASE_URL", "https://api.openai.com/v1")


def llm_model() -> str:
    return get("LLM_MODEL", "gpt-4o-mini")


def template_dir() -> Optional[Path]:
    raw = get("TEMPLATE_DIR")
    if not raw:
        return None
    return Path(raw).expanduser()


def is_placeholder(value: str) -> bool:
    """判断是不是还没填的占位值。"""
    if not value:
        return True
    lowered = value.lower()
    return any(
        token in lowered
        for token in ("your_", "xxx", "<", "填入", "待填", "todo")
    )
