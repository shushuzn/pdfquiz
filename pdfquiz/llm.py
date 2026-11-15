"""最小 OpenAI 兼容客户端。只用标准库，避免为一个 POST 装 SDK。"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"


class LLMError(RuntimeError):
    pass


def chat(
    system: str,
    user: str,
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    temperature: float = 0.2,
    json_mode: bool = True,
    timeout: int = 180,
) -> str:
    key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("PDFQUIZ_API_KEY")
    if not key:
        raise LLMError(
            "未配置 API Key。设置环境变量 OPENAI_API_KEY，或用 --api-key 传入。\n"
            "（本地模型可设 OPENAI_BASE_URL=http://localhost:11434/v1）"
        )

    base = (base_url or os.getenv("OPENAI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    mdl = model or os.getenv("PDFQUIZ_MODEL") or DEFAULT_MODEL

    payload: dict = {
        "model": mdl,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")[:400]
        if exc.code == 400 and "response_format" in detail and json_mode:
            return chat(
                system, user, model=mdl, base_url=base, api_key=key,
                temperature=temperature, json_mode=False, timeout=timeout,
            )
        raise LLMError(f"接口返回 {exc.code}：{detail}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"无法连接 {base}：{exc.reason}") from exc

    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise LLMError(f"响应结构异常：{str(body)[:300]}") from exc


def parse_json(raw: str) -> dict:
    """容忍模型加 ```json 围栏或前后寒暄。"""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise LLMError(f"模型未返回合法 JSON：{raw[:300]}")
