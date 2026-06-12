"""
Работа с Claude API (Anthropic / реселлеры).

Два режима: "assistant" и "sales".
История диалога — последние 10 реплик на пользователя (в памяти процесса).
Дневной лимит запросов проверяется в handlers/.

АВТООПРЕДЕЛЕНИЕ ФОРМАТА:
Реселлеры бывают двух «диалектов» — Anthropic (/messages, x-api-key,
content[]) и OpenAI-совместимый (/chat/completions, Bearer, choices[]).
Заранее неизвестно, какой у конкретного реселлера. Поэтому при первом
запросе код перебирает оба варианта и запоминает тот, что вернул 200.
Дальше использует только его. Это убирает любые догадки о формате.
"""
import logging

import anthropic
import httpx

import prompts
from config import config

logger = logging.getLogger(__name__)

# Для реселлеров — всегда прямой httpx (SDK ломает URL и режет заголовки).
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

# Запомненный рабочий диалект ("anthropic" | "openai"). None = ещё не определён.
_working_dialect: str | None = None


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


def _base() -> str:
    return (config.anthropic_base_url or "https://api.anthropic.com/v1").rstrip("/")


def _build_anthropic(system: str, messages: list[dict]) -> tuple[str, dict, dict]:
    """URL, заголовки, тело для Anthropic-диалекта (/messages)."""
    url = f"{_base()}/messages"
    headers = {
        "x-api-key":         config.anthropic_api_key,
        "Authorization":     f"Bearer {config.anthropic_api_key}",
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }
    payload = {
        "model":      config.ai_model,
        "max_tokens": config.ai_max_tokens,
        "system":     system,
        "messages":   messages,
    }
    return url, headers, payload


def _build_openai(system: str, messages: list[dict]) -> tuple[str, dict, dict]:
    """URL, заголовки, тело для OpenAI-совместимого диалекта (/chat/completions)."""
    url = f"{_base()}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.anthropic_api_key}",
        "content-type":  "application/json",
    }
    payload = {
        "model":      config.ai_model,
        "max_tokens": config.ai_max_tokens,
        "messages":   [{"role": "system", "content": system}, *messages],
    }
    return url, headers, payload


_BUILDERS = {
    "openai":    _build_openai,
    "anthropic": _build_anthropic,
}


async def _post(url: str, headers: dict, payload: dict) -> httpx.Response:
    proxy = config.proxy_url  # None = без прокси; задаётся через PROXY_URL в .env
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, proxy=proxy) as client:
            return await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as e:
        raise anthropic.APIConnectionError(
            message=f"Сбой соединения с {url}: {e}",
            request=httpx.Request("POST", url),
        ) from e


def _status_error(resp: httpx.Response) -> Exception:
    """Подбирает нужное anthropic-исключение по HTTP-коду (их ловят handlers/)."""
    snippet = resp.text[:300]
    if resp.status_code == 401:
        return anthropic.AuthenticationError(
            message=f"Неверный API-ключ (401): {snippet}", response=resp, body=resp.text)
    if resp.status_code == 403:
        return anthropic.PermissionDeniedError(
            message=f"Запрос заблокирован (403): {snippet}", response=resp, body=resp.text)
    if resp.status_code == 404:
        return anthropic.NotFoundError(
            message=f"Не найдено (404) — проверь AI_MODEL/BASE_URL: {snippet}",
            response=resp, body=resp.text)
    return anthropic.APIStatusError(
        message=f"HTTP {resp.status_code}: {snippet}", response=resp, body=resp.text)


async def _ask_direct(system: str, messages: list[dict]) -> tuple[dict, str]:
    """
    Делает запрос к реселлеру. Возвращает (json-ответ, диалект).

    Если рабочий диалект уже определён — бьёт только в него.
    Если нет — пробует оба (сначала OpenAI: ключи sk-... обычно
    OpenAI-совместимые), запоминает первый успешный.
    """
    global _working_dialect

    # Порядок проб: если диалект известен — только он; иначе оба.
    order = [_working_dialect] if _working_dialect else ["openai", "anthropic"]

    last_error: Exception | None = None
    for dialect in order:
        url, headers, payload = _BUILDERS[dialect](system, messages)
        resp = await _post(url, headers, payload)

        if resp.status_code == 200:
            if _working_dialect != dialect:
                _working_dialect = dialect
                logger.info("Рабочий диалект API определён: %s (%s)", dialect, url)
            try:
                return resp.json(), dialect
            except ValueError:
                raise anthropic.APIStatusError(
                    message=f"API вернул не-JSON: {resp.text[:300]}",
                    response=resp, body=resp.text)

        # Не 200 — запоминаем ошибку и пробуем следующий диалект (если он есть).
        logger.warning("Диалект %s → HTTP %s: %s", dialect, resp.status_code, resp.text[:200])
        last_error = _status_error(resp)

    # Ни один диалект не сработал — бросаем последнюю ошибку.
    if last_error:
        raise last_error
    raise anthropic.APIConnectionError(
        message="Не удалось обратиться к API ни одним способом",
        request=httpx.Request("POST", _base()))


def _extract_answer(data: dict, dialect: str) -> tuple[str, str, int, int]:
    """Достаёт (текст, stop_reason, input_tokens, output_tokens) из ответа."""
    usage = data.get("usage") or {}

    if dialect == "anthropic" or "content" in data:
        answer = "".join(
            b.get("text", "") for b in (data.get("content") or [])
            if isinstance(b, dict) and b.get("type") == "text"
        ).strip()
        return (answer, data.get("stop_reason") or "",
                usage.get("input_tokens", 0), usage.get("output_tokens", 0))

    if dialect == "openai" or "choices" in data:
        choice = (data.get("choices") or [{}])[0]
        answer = ((choice.get("message") or {}).get("content") or "").strip()
        return (answer, choice.get("finish_reason") or "",
                usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))

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
            data, dialect = await _ask_direct(system, list(history))
            answer, stop_reason, in_tok, out_tok = _extract_answer(data, dialect)
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
