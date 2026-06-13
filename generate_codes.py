"""
Генератор кодов доступа под тарифную систему.

Запуск:  python generate_codes.py
Вывод:   access_codes.txt (в той же папке)

Формат кода:  PREFIX-XXXX-XXXX-XXXX   (12 случайных символов без 0/O/1/I/L)
Примеры:
    STD-A3F2-9B2E-C074   → СТАРТ
    PRO-7D3A-1F88-E205   → ПРО
    BIZ-0C9F-3A1D-B774   → БИЗНЕС
    PREM-2E4B-A0F3-D918  → ПРЕМИУМ
    MAST-5F7C-0D2A-E831  → МАСТЕР (команда)

Количество кодов — константы COUNTS ниже.
Коды также сразу загружаются в bot.db (если он доступен).
"""
import secrets
import sys
import os

# --- Настройки (меняй сколько нужно кодов каждого тарифа) ---
COUNTS = {
    "STD":  100,   # СТАРТ   — 990 ₽/мес
    "PRO":  100,   # ПРО     — 1 990 ₽/мес
    "BIZ":  50,    # БИЗНЕС  — 4 990 ₽/мес
    "PREM": 50,    # ПРЕМИУМ — 6 990 ₽/мес
    "MAST": 10,    # МАСТЕР  — служебный (команда)
}
# -------------------------------------------------------------

# Алфавит без путаемых символов (нет 0, O, 1, I, L).
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
GROUPS = 3
GROUP_LEN = 4


def make_code(prefix: str) -> str:
    parts = ["".join(secrets.choice(ALPHABET) for _ in range(GROUP_LEN)) for _ in range(GROUPS)]
    return f"{prefix}-{'-'.join(parts)}"


def generate_batch(prefix: str, count: int) -> list[str]:
    codes: set[str] = set()
    while len(codes) < count:
        codes.add(make_code(prefix))
    return sorted(codes)


def main() -> None:
    all_codes: list[str] = []
    for prefix, count in COUNTS.items():
        batch = generate_batch(prefix, count)
        all_codes.extend(batch)
        print(f"  {prefix:>4}-  {len(batch):>4} шт")

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "access_codes.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(all_codes) + "\n")
    print(f"\nВсего: {len(all_codes)} кодов → {out}")

    # Загрузка в БД (необязательно — бот сделает это при старте сам).
    try:
        import asyncio
        from models.database import init_db, load_codes, codes_count

        async def _load() -> None:
            await init_db()
            added = await load_codes(all_codes)
            total = await codes_count()
            print(f"БД: добавлено {added}, всего в базе {total}")

        asyncio.run(_load())
    except Exception as e:
        print(f"(БД пропущена: {e} — бот загрузит коды при старте)")

    print("\nПримеры кодов:")
    for prefix in COUNTS:
        sample = next(c for c in all_codes if c.startswith(prefix + "-"))
        print(f"  {sample}")
    print("\n⚠️  access_codes.txt — ключи к боту. Храни в секрете, не коммить в GitHub!")


if __name__ == "__main__":
    main()
