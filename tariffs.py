"""
Тарифы бота «Артём» — единый источник правды.

Тариф «зашит» в префиксе кода активации:
    STD-...   → СТАРТ
    PRO-...   → ПРО
    BIZ-...   → БИЗНЕС
    PREM-...  → ПРЕМИУМ
    MAST-...  → МАСТЕР (служебный, для команды)

Старые коды без известного префикса (WRN-...) трактуются как СТАРТ —
чтобы ранее выданные ключи продолжали работать.

Лимиты:
- рассылки  — месячный счётчик (mailings_month), None = безлимит
- ИИ         — дневной счётчик  (ai_daily),        None = безлимит
- темп       — пауза между сообщениями в секундах (антибан аккаунтов)
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Tariff:
    key: str                    # внутренний идентификатор (хранится в БД)
    prefix: str                 # префикс кода активации
    title: str                  # отображаемое название
    price: int | None           # ₽/мес; None = служебный (не продаётся)
    mailings_month: int | None  # лимит рассылок в месяц; None = безлимит
    ai_daily: int | None        # лимит ИИ-запросов в день; None = безлимит
    pace_seconds: int           # пауза между сообщениями рассылки, сек


# Порядок = порядок отображения (от младшего к старшему).
TARIFFS: dict[str, Tariff] = {
    "start":    Tariff("start",    "STD",  "СТАРТ",    990,  3_000,   20, 300),
    "pro":      Tariff("pro",      "PRO",  "ПРО",     1990,  6_000,   30, 300),
    "business": Tariff("business", "BIZ",  "БИЗНЕС",  4990, 15_000,   80, 180),
    "premium":  Tariff("premium",  "PREM", "ПРЕМИУМ", 6990, 30_000,  150,  90),
    "master":   Tariff("master",   "MAST", "МАСТЕР",  None,   None, None, 120),
}

# Тариф по умолчанию для легаси-кодов (WRN-...) и неизвестных префиксов.
DEFAULT_TARIFF = "start"

_PREFIX_TO_KEY = {t.prefix: t.key for t in TARIFFS.values()}


def tariff_for_code(code: str) -> str:
    """Определяет ключ тарифа по префиксу кода. Неизвестный → DEFAULT_TARIFF."""
    prefix = code.strip().upper().split("-", 1)[0]
    return _PREFIX_TO_KEY.get(prefix, DEFAULT_TARIFF)


def get_tariff(key: str | None) -> Tariff:
    """Возвращает тариф по ключу. Пустой/неизвестный ключ → DEFAULT_TARIFF."""
    return TARIFFS.get(key or DEFAULT_TARIFF, TARIFFS[DEFAULT_TARIFF])


# Известные префиксы кодов + легаси WRN (старые коды до тарифной системы).
_CODE_PREFIXES = [t.prefix for t in TARIFFS.values()] + ["WRN"]
_CODE_RE = re.compile(r"^(" + "|".join(_CODE_PREFIXES) + r")(-[A-Z0-9]{2,6}){2,4}$")


def looks_like_code(text: str) -> bool:
    """Похож ли текст на код доступа (PREFIX-XXXX-XXXX-XXXX). Регистр игнорим."""
    return bool(_CODE_RE.match(text.strip().upper()))


def pace_human(tariff: Tariff) -> str:
    """Темп в человекочитаемом виде, напр. «1 сообщение / 5 мин»."""
    sec = tariff.pace_seconds
    if sec % 60 == 0:
        return f"1 сообщение / {sec // 60} мин"
    return f"1 сообщение / {sec / 60:.1f} мин".replace(".0 ", " ")
