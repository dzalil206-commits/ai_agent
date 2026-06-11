"""
Работа с Claude API (Anthropic / реселлеры).

Два режима: "assistant" и "sales".
История диалога — последние 10 реплик на пользователя (в памяти процесса).
Дневной лимит запросов проверяется в handlers/.
"""
import json
import logging

import anthropic
import httpx

import prompts
from config import config

logger = logging.getLogger(__name__)

# Используем прямые httpx-запросы для реселлеров (обходим специфические
# заголовки anthropic SDK, которые некоторые реселлеры отклоняют).
# Для официального api.anthropic.com используем SDK как обычно.
# Всегда используем прямой httpx для реселлеров — SDK добавляет /v1/messages
# к base_url, что при base_url=.../v1 даёт двойной /v1 (403 Forbidden).
# Direct-режим формирует URL сам: base.rstrip(/v1) + /v1/messages.
_use_direct_http = bool(config.anthropic_base_url)

# SDK используется только без реселлера (официальный Anthropic).
_client = (
    anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)
    if config.anthropic_api_key and not _use_direct_http
    else None
)

SYSTEM_BY_MODE = {
    "assistant": prompts.ASSISTANT_SYSTEM,
    "sales":     prompts.SALES_SYSTEM,
}

_history: dict[tuple[int, str], list[dict]] = {}
HISTORY_MAX_MESSAGES = 10

_modes: dict[int, str] = {}


def set_mode(user_id: int, mode: str) -> None:
    _modes[user_id] = mode
    reset_history(user_id, mode)


def clear_mode(user_id: int) -> None:
    _modes.pop(user_id, None)


def get_mode(user_id: int) -> str | None:
    return _modes.get(user_id)


def is_configured() -> bool:
    return bool(config.anthropic_api_key)


def reset_history(user_id: int, mode: str | None = None) -> None:
    if mode is not None:
        _history.pop((user_id, mode), None)
    else:
        for key in [k for k in _history if k[0] == user_id]:
            _history.pop(key, None)


async def _ask_direct(system: str, messages: list[dict]) -> dict:
    """Прямой httpx-запрос к API реселлера (минимум заголовков)."""
    base = (config.anthropic_base_url or "https://api.anthropic.com/v1").rstrip("/")
    url = f"{base}/messages"
    headers = {
        "x-api-key": config.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model":      config.ai_model,
        "max_tokens": config.ai_max_tokens,
        "system":     system,
        "messages":   messages,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=headers, content=json.dumps(payload))

    if resp.status_code == 401:
        raise anthropic.AuthenticationError(
            response=resp, body=resp.text,
            message="Неверный API-ключ (401)"
        )
    if resp.status_code == 403:
        raise anthropic.PermissionDeniedError(
            response=resp, body=resp.text,
            message=f"Запрос заблокирован реселлером (403): {resp.text[:200]}"
        )
    if resp.status_code != 200:
        raise anthropic.APIStatusError(
            message=f"HTTP {resp.status_code}: {resp.text[:200]}",
            response=resp, body=resp.text,
        )
    return resp.json()


async def ask(user_id: int, mode: str, text: str) -> str:
    """
    Отправляет сообщение в Claude и возвращает ответ.
    Бросает исключения anthropic.* — обработка в handlers/.
    """
    if not config.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY не задан")

    key = (user_id, mode)
    history = _history.setdefault(key, [])
    history.append({"role": "user", "content": text})
    system = SYSTEM_BY_MODE.get(mode, prompts.ASSISTANT_SYSTEM)

    if _use_direct_http:
        data = await _ask_direct(system, list(history))
        content_blocks = data.get("content", [])
        answer = "".join(
            b["text"] for b in content_blocks if b.get("type") == "text"
        ).strip()
        stop_reason = data.get("stop_reason", "")
        usage = data.get("usage", {})
        in_tok  = usage.get("input_tokens", 0)
        out_tok = usage.get("output_tokens", 0)
    else:
        response = await _client.messages.create(
            model=config.ai_model,
            max_tokens=config.ai_max_tokens,
            system=system,
            messages=list(history),
        )
        answer = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()
        stop_reason = response.stop_reason
        in_tok  = response.usage.input_tokens
        out_tok = response.usage.output_tokens

    if stop_reason == "refusal" or not answer:
        history.pop()
        return ""

    history.append({"role": "assistant", "content": answer})

    if len(history) > HISTORY_MAX_MESSAGES:
        del history[: len(history) - HISTORY_MAX_MESSAGES]

    logger.info("AI %s user=%s in=%s out=%s", mode, user_id, in_tok, out_tok)
    return answer
