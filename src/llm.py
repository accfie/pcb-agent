# -*- coding: utf-8 -*-
"""大模型调用封装。

两个要点：
1. 走 OpenAI 兼容接口，换厂商只改 .env 里的 LLM_BASE_URL；
2. 解析失败时把报错信息回喂给模型重试 —— 这就是课程要的「反馈闭环」。

没有密钥时自动降级为 mock 模式，返回本地样例数据，
让你在没有密钥的情况下也能把整条链路跑通、把演示录完。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MOCK_ENV = "PCB_AGENT_MOCK"


class LLMError(RuntimeError):
    pass


def is_mock() -> bool:
    return os.environ.get(MOCK_ENV, "").strip() in ("1", "true", "yes")


def mode_label() -> str:
    """报告里要如实写明结果是怎么来的，三种情况不能混。"""
    if is_mock():
        return "mock（本地样例，未调用模型）"
    if os.environ.get("PCB_AGENT_MODE", "").strip() == "manual":
        return "人工中转（网页版模型生成，人工复制回填，非 API 自动调用）"
    return "真实模型调用（API）"


def _extract_json(text: str) -> dict:
    """从模型输出里抠出 JSON。容忍 ```json 包裹和前后废话。"""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def chat_json(system: str, user: str, max_retries: int = 2) -> dict:
    """要求模型输出 JSON，失败自动带着错误信息重试。"""
    from src import settings

    if is_mock():
        raise LLMError("mock 模式不应走进 chat_json")

    api_key = settings.llm_api_key()
    if settings.is_placeholder(api_key):
        raise LLMError("LLM_API_KEY 未配置（可用 --mock 先跑通链路）")

    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:
        raise LLMError("没装 openai 库，执行 pip install -r requirements.txt") from exc

    client = OpenAI(api_key=api_key, base_url=settings.llm_base_url())
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    last_err = ""
    use_json_mode = True
    for attempt in range(max_retries + 1):
        try:
            kwargs = dict(
                model=settings.llm_model(),
                messages=messages,
                temperature=0,
            )
            if use_json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            resp = client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            # 有些本地模型服务不支持 response_format，降级再试一次
            if use_json_mode and ("response_format" in msg or "not support" in msg.lower()):
                use_json_mode = False
                continue
            raise LLMError(
                "调用模型失败：%s\n       检查 .env 里的 LLM_BASE_URL / LLM_MODEL / LLM_API_KEY 是否正确。"
                % msg[:300]
            ) from exc

        content = resp.choices[0].message.content or ""
        try:
            return _extract_json(content)
        except json.JSONDecodeError as exc:
            last_err = str(exc)
            if attempt >= max_retries:
                break
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "上面这段不是合法 JSON（错误：%s）。"
                        "只重新输出一个合法的 JSON 对象，不要任何解释和代码块标记。" % last_err
                    ),
                }
            )
    raise LLMError("模型连续 %d 次没有返回合法 JSON：%s" % (max_retries + 1, last_err))


def load_mock_netlist() -> dict:
    path = ROOT / "data" / "sample_netlist.json"
    return json.loads(path.read_text(encoding="utf-8"))
