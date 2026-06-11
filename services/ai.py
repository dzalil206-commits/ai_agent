"""
Работа с Claude API (Anthropic / реселлеры).

Два режима: "assistant" и "sales".
История диалога — последние 10 реплик на пользователя (в памяти процесса).
Дневной лимит запросов проверяется в handlers/.
"""
import logging

import anthropic
import httpx

import prompts
from config import config

logger = logging.getLogger(__name__)

# Для реселлеров — всегда прямой httpx: SDK добавляет /v1/messages к base_url,
# что при base_url=.../v1 даёт двойной /v1 и 403. Direct-режим строит URL сам.
_use_direct_http = bool(config.anthropic_base_url)

# SDK используется только с официальным Anthropic (без base_url).
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

REQUEST_TIMEOUT = 120  # сек; длинный ответ ИИ может генерироваться до минуты


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

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as e:
        # Сеть/таймаут/DNS — приводим к anthropic-исключению, его ловят handlers/.
        raise anthropic.APIConnectionError(
            message=f"Сбой соединения с {url}: {e}",
            request=httpx.Request("POST", url),
        ) from e

    if resp.status_code == 401:
        raise anthropic.AuthenticationError(
            message="Неверный API-ключ (401)",
            response=resp, body=resp.text,
        )
    if resp.status_code == 403:
        raise anthropic.PermissionDeniedError(
            message=f"Запрос заблокирован (403): {resp.text[:200]}",
            response=resp, body=resp.text,
        )
    if resp.status_code == 404:
        raise anthropic.NotFoundError(
            message=f"Не найдено (404) — проверь AI_MODEL и BASE_URL: {resp.text[:200]}",
            response=resp, body=resp.text,
        )
    if resp.status_code != 200:
        raise anthropic.APIStatusError(
            message=f"HTTP {resp.status_code}: {resp.text[:200]}",
            response=resp, body=resp.text,
        )

    try:
        return resp.json()
    except ValueError:
        raise anthropic.APIStatusError(
            message=f"API вернул не-JSON: {resp.text[:200]}",
            response=resp, body=resp.text,
        )


def _extract_answer(data: dict) -> tuple[str, str, int, int]:
    """
    Достаёт (текст, stop_reason, input_tokens, output_tokens) из ответа.
    Поддерживает оба формата: Anthropic (content[]) и OpenAI (choices[]) —
    реселлеры отдают какой-то из них.
    """
    usage = data.get("usage") or {}

    if "content" in data:  # Anthropic-формат
        answer = "".join(
            b.get("text", "") for b in (data.get("content") or [])
            if isinstance(b, dict) and b.get("type") == "text"
        ).strip()
        return (
            answer,
            data.get("stop_reason") or "",
            usage.get("input_tokens", 0),
            usage.get("output_tokens", 0),
        )

    if "choices" in data:  # OpenAI-совместимый формат
        choice = (data.get("choices") or [{}])[0]
        answer = ((choice.get("message") or {}).get("content") or "").strip()
        return (
            answer,
            choice.get("finish_reason") or "",
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
        )

    logger.error("Неизвестный формат ответа API: %s", str(data)[:300])
    return "", "", 0, 0


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

    try:
        if _use_direct_http:
            data = await _ask_direct(system, list(history))
            answer, stop_reason, in_tok, out_tok = _extract_answer(data)
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
    except Exception:
        # Запрос не удался — убираем вопрос из истории, чтобы при повторе
        # не накапливались дубли подряд идущих user-сообщений.
        history.pop()
        raise

    if stop_reason == "refusal" or not answer:
        history.pop()
        return ""

    history.append({"role": "assistant", "content": answer})

    if len(history) > HISTORY_MAX_MESSAGES:
        del history[: len(history) - HISTORY_MAX_MESSAGES]

    logger.info("AI %s user=%s in=%s out=%s", mode, user_id, in_tok, out_tok)
    return answer
