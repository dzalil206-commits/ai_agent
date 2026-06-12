"""
Диагностика реселлер-API. Запусти на BotHost:  python probe_api.py

Читает ключ и base_url из /app/data/.env (или локального .env), простукивает
оба диалекта (Anthropic /messages и OpenAI /chat/completions) разными
заголовками и печатает сырой ответ сервера. По выводу сразу видно:
- какой эндпоинт/заголовок даёт 200 (рабочий формат),
- или что ключ невалиден (все варианты 401) — тогда нужен новый ключ.

Никаких разделителей команд (;) не требует — это обычный скрипт.
"""
import json
import os
import urllib.error
import urllib.request


def _read_env(path: str) -> dict:
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


env = {}
for p in ("/app/data/.env", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")):
    env.update(_read_env(p))
env.update(os.environ)  # реальное окружение главнее

KEY = (env.get("ANTHROPIC_API_KEY") or "").strip()
BASE = (env.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com/v1").strip().rstrip("/")
MODEL = (env.get("AI_MODEL") or "claude-sonnet-4-6").strip()

print("=" * 60)
print("BASE :", BASE)
print("MODEL:", MODEL)
print("KEY  :", (KEY[:8] + "..." + KEY[-4:]) if KEY else "(ПУСТО!)")
print("=" * 60)

if not KEY:
    print("\n❌ Ключ не найден в /app/data/.env — заполни ANTHROPIC_API_KEY.")
    raise SystemExit(1)


def post(url, headers, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read(500).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(500).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return "ERR", str(e)[:400]


anthropic_body = {"model": MODEL, "max_tokens": 50,
                  "messages": [{"role": "user", "content": "ping"}]}
openai_body = {"model": MODEL, "max_tokens": 50,
               "messages": [{"role": "user", "content": "ping"}]}

tests = [
    ("OpenAI  /chat/completions  + Bearer",
     f"{BASE}/chat/completions",
     {"Authorization": f"Bearer {KEY}", "content-type": "application/json"},
     openai_body),
    ("Anthropic /messages        + x-api-key",
     f"{BASE}/messages",
     {"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
     anthropic_body),
    ("Anthropic /messages        + Bearer",
     f"{BASE}/messages",
     {"Authorization": f"Bearer {KEY}", "anthropic-version": "2023-06-01", "content-type": "application/json"},
     anthropic_body),
]

winner = None
for name, url, headers, body in tests:
    status, text = post(url, headers, body)
    mark = "✅" if status == 200 else "  "
    print(f"\n{mark} {name}")
    print(f"   {url}")
    print(f"   STATUS: {status}")
    print(f"   BODY:   {text[:400]}")
    if status == 200 and winner is None:
        winner = name

print("\n" + "=" * 60)
if winner:
    print(f"✅ РАБОЧИЙ ФОРМАТ: {winner}")
    print("   Бот уже умеет его определять автоматически — просто перезапусти.")
else:
    print("❌ Ни один формат не дал 200.")
    print("   Если везде 401 — ключ невалиден, возьми новый в кабинете aiprimetech.")
    print("   Если 403 'host not in allowlist' — это egress-блок, не наш код.")
print("=" * 60)
