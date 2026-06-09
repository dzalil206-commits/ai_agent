"""
Генератор кодов доступа.

Создаёт уникальные коды формата WRN-XXXX-XXXX-XXXX-XXXX
(буквы и цифры без путаемых символов 0/O/1/I/L).

Запуск:
    python generate_codes.py            # 5000 кодов
    python generate_codes.py 1000       # произвольное количество

Результат:
- access_codes.txt — список кодов (РАЗДАВАЙ ЮЗЕРАМ ОТСЮДА, храни в секрете)
- коды также загружаются в базу бота (bot.db)
"""
import secrets
import sys

# Алфавит без путаемых символов: нет 0, O, 1, I, L.
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
GROUPS = 4          # сколько групп после WRN-
GROUP_LEN = 3       # длина каждой группы


def make_code():
    groups = []
    for _ in range(GROUPS):
        groups.append("".join(secrets.choice(ALPHABET) for _ in range(GROUP_LEN)))
    return "WRN-" + "-".join(groups)


def generate_unique(n):
    """Генерирует n гарантированно уникальных кодов."""
    codes = set()
    while len(codes) < n:
        codes.add(make_code())
    return sorted(codes)


def main():
    n = 5000
    if len(sys.argv) > 1:
        n = int(sys.argv[1])

    print("Генерирую {} уникальных кодов...".format(n))
    codes = generate_unique(n)

    with open("access_codes.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(codes))
    print("OK Сохранено в access_codes.txt ({} кодов)".format(len(codes)))

    import asyncio
    from models.database import init_db, load_codes, codes_count

    async def _load():
        await init_db()
        added = await load_codes(codes)
        total = await codes_count()
        print("OK Загружено в базу: добавлено {}, всего в базе {}".format(added, total))

    asyncio.run(_load())

    print("\nПримеры кодов:")
    for c in codes[:5]:
        print("  ", c)
    print("\nВНИМАНИЕ: access_codes.txt — это ключи к боту. Храни в секрете!")


if __name__ == "__main__":
    main()
