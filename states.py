"""
Лёгкое in-memory состояние диалога (живёт в процессе бота).

Сейчас хранит только флаг «юзер нажал Сменить тариф и вводит новый токен».
Кнопку обрабатывает handlers/callbacks.py, а сам токен ловит
handlers/commands.py — поэтому состояние общее, в отдельном модуле.
"""

_awaiting_new_code: set[int] = set()


def set_awaiting_code(user_id: int) -> None:
    _awaiting_new_code.add(user_id)


def clear_awaiting_code(user_id: int) -> None:
    _awaiting_new_code.discard(user_id)


def is_awaiting_code(user_id: int) -> bool:
    return user_id in _awaiting_new_code
