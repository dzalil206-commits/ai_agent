"""
Работа с Claude API (Anthropic).

- Асинхронный клиент (бот на aiogram — всё асинхронное).
- Два режима: "assistant" (ИИ ассистент) и "sales" (ИИ общение с клиентами).
- История диалога хранится в памяти процесса (последние 10 реплик на юзера);
  при перезапуске бота история обнуляется — для Этапа 2 этого достаточно.
- Дневной лимит запросов проверяется в handlers/, не здесь.
"""
import logging

import anthropic

import prompts
from config import config

logger = logging.getLogger(__name__)

# Клиент создаётся один раз. Если ключа нет — None, ИИ отключён.
# base_url нужен для ключей от реселлеров (не sk-ant-...): они работают
# через свой адрес API, совместимый с Anthropic.
_client = (
    anthropic.AsyncAnthropic(
        api_key=config.anthropic_api_key,
        base_url=config.anthropic_base_url,  # None = официальный api.anthropic.com
    )
    if config.anthropic_api_key
    else None
)

SYSTEM_BY_MODE = {
    "assistant": prompts.ASSISTANT_SYSTEM,
    "sales": prompts.SALES_SYSTEM,
}

# История диалогов: {(user_id, mode): [{"role": ..., "content": ...}, ...]}
_history: dict[tuple[int, str], list[dict]] = {}
HISTORY_MAX_MESSAGES = 10  # последних реплик (5 пар вопрос-ответ)

# Текущий ИИ-режим юзера: {user_id: "assistant" | "sales"}.
# Хранится в памяти; после перезапуска бота юзер заново выбирает режим в меню.
_modes: dict[int, str] = {}


def set_mode(user_id: int, mode: str) -> None:
    """Включает юзеру ИИ-режим и начинает диалог с чистого листа."""
    _modes[user_id] = mode
    reset_history(user_id, mode)


def clear_mode(user_id: int) -> None:
    _modes.pop(user_id, None)


def get_mode(user_id: int) -> str | None:
    return _modes.get(user_id)


def is_configured() -> bool:
    """Прописан ли API-ключ (без него ИИ-режимы отключены)."""
    return _client is not None


def reset_history(user_id: int, mode: str | None = None) -> None:
    """Сбрасывает историю диалога юзера (одного режима или всех)."""
    if mode is not None:
        _history.pop((user_id, mode), None)
    else:
        for key in [k for k in _history if k[0] == user_id]:
            _history.pop(key, None)


async def ask(user_id: int, mode: str, text: str) -> str:
    """
    Отправляет сообщение юзера в Claude и возвращает ответ.
    Бросает исключения anthropic.* — обработка в handlers/.
    """
    if _client is None:
        raise RuntimeError("ANTHROPIC_API_KEY не задан")

    key = (user_id, mode)
    history = _history.setdefault(key, [])
    history.append({"role": "user", "content": text})

    response = await _client.messages.create(
        model=config.ai_model,
        max_tokens=config.ai_max_tokens,
        system=SYSTEM_BY_MODE.get(mode, prompts.ASSISTANT_SYSTEM),
        messages=list(history),
    )

    # Собираем текст из всех текстовых блоков ответа.
    answer = "".join(
        block.text for block in response.content if block.type == "text"
    ).strip()

    if response.stop_reason == "refusal" or not answer:
        # Модель отказалась отвечать — не пишем пустоту в историю.
        history.pop()
        return ""

    history.append({"role": "assistant", "content": answer})

    # Обрезаем историю, чтобы не раздувать расход токенов.
    if len(history) > HISTORY_MAX_MESSAGES:
        del history[: len(history) - HISTORY_MAX_MESSAGES]

    logger.info(
        "AI %s user=%s in=%s out=%s",
        mode, user_id,
        response.usage.input_tokens, response.usage.output_tokens,
    )
    return answer
