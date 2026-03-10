"""
VK AI Bot — Long Poll версия (запуск локально)
Получает сообщения из сообщества ВКонтакте и отвечает через нейросеть.
"""

import requests
import time
import json
import logging
from config import (
    VK_TOKEN, VK_GROUP_ID, VK_API_VERSION,
    AI_PROVIDER, ANTHROPIC_API_KEY, OPENAI_API_KEY,
    AI_SYSTEM_PROMPT, MAX_HISTORY_MESSAGES
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

# Хранилище истории диалогов: {user_id: [{"role": ..., "content": ...}]}
dialog_history = {}


# ─────────────────────────── VK API ───────────────────────────

def vk_call(method, params):
    """Вызов метода VK API."""
    params["access_token"] = VK_TOKEN
    params["v"] = VK_API_VERSION
    resp = requests.post(f"https://api.vk.com/method/{method}", data=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"VK API error {data['error']['error_code']}: {data['error']['error_msg']}")
    return data.get("response", {})


def send_message(user_id, text):
    """Отправить сообщение пользователю."""
    vk_call("messages.send", {
        "user_id": user_id,
        "message": text,
        "random_id": int(time.time() * 1000),
    })
    log.info(f"→ [{user_id}] {text[:80]}{'...' if len(text) > 80 else ''}")


def get_longpoll_server():
    """Получить параметры Long Poll сервера."""
    return vk_call("groups.getLongPollServer", {"group_id": VK_GROUP_ID})


# ─────────────────────────── AI ───────────────────────────

def ask_claude(user_id, user_text):
    """Запрос к Claude (Anthropic)."""
    history = dialog_history.setdefault(user_id, [])
    history.append({"role": "user", "content": user_text})

    # Ограничиваем историю
    if len(history) > MAX_HISTORY_MESSAGES * 2:
        history[:] = history[-MAX_HISTORY_MESSAGES * 2:]

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-opus-4-5",
            "max_tokens": 1024,
            "system": AI_SYSTEM_PROMPT,
            "messages": history,
        },
        timeout=30,
    )
    resp.raise_for_status()
    answer = resp.json()["content"][0]["text"]
    history.append({"role": "assistant", "content": answer})
    return answer


def ask_openai(user_id, user_text):
    """Запрос к OpenAI (GPT)."""
    history = dialog_history.setdefault(user_id, [])
    history.append({"role": "user", "content": user_text})

    if len(history) > MAX_HISTORY_MESSAGES * 2:
        history[:] = history[-MAX_HISTORY_MESSAGES * 2:]

    messages = [{"role": "system", "content": AI_SYSTEM_PROMPT}] + history

    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-4o-mini",
            "messages": messages,
            "max_tokens": 1024,
        },
        timeout=30,
    )
    resp.raise_for_status()
    answer = resp.json()["choices"][0]["message"]["content"]
    history.append({"role": "assistant", "content": answer})
    return answer


def ask_ai(user_id, text):
    """Выбрать нужного AI провайдера."""
    if AI_PROVIDER == "claude":
        return ask_claude(user_id, text)
    elif AI_PROVIDER == "openai":
        return ask_openai(user_id, text)
    else:
        raise ValueError(f"Неизвестный AI провайдер: {AI_PROVIDER}")


# ─────────────────────────── Обработка событий ───────────────────────────

def handle_event(event):
    """Обработать одно событие от VK."""
    if event.get("type") != "message_new":
        return

    msg = event.get("object", {}).get("message", {})
    user_id = msg.get("from_id")
    text = msg.get("text", "").strip()

    # Пропускаем пустые сообщения и сообщения от самого сообщества
    if not text or user_id <= 0:
        return

    log.info(f"← [{user_id}] {text}")

    # Команда /reset — сброс истории
    if text.lower() in ("/reset", "сброс", "/start"):
        dialog_history.pop(user_id, None)
        send_message(user_id, "История диалога очищена. Начнём заново! 👋")
        return

    try:
        # Показываем "печатает..."
        vk_call("messages.setActivity", {"user_id": user_id, "type": "typing", "group_id": VK_GROUP_ID})
        answer = ask_ai(user_id, text)
        send_message(user_id, answer)
    except Exception as e:
        log.error(f"Ошибка при обработке сообщения от {user_id}: {e}")
        send_message(user_id, "Произошла ошибка. Попробуйте ещё раз чуть позже 🙏")


# ─────────────────────────── Long Poll цикл ───────────────────────────

def run_longpoll():
    """Основной цикл Long Poll."""
    log.info("🤖 VK AI Bot запускается...")
    log.info(f"   Группа: {VK_GROUP_ID}")
    log.info(f"   AI: {AI_PROVIDER.upper()}")

    server_info = get_longpoll_server()
    server = server_info["server"]
    key = server_info["key"]
    ts = server_info["ts"]

    log.info("✅ Подключился к Long Poll серверу. Жду сообщений...\n")

    while True:
        try:
            resp = requests.get(
                f"{server}?act=a_check&key={key}&ts={ts}&wait=25",
                timeout=30,
            )
            data = resp.json()

            if "failed" in data:
                failed = data["failed"]
                if failed == 1:
                    ts = data["ts"]
                elif failed in (2, 3):
                    log.warning("Long Poll ключ устарел, переподключаюсь...")
                    server_info = get_longpoll_server()
                    server = server_info["server"]
                    key = server_info["key"]
                    ts = server_info["ts"]
                continue

            ts = data["ts"]
            for event in data.get("updates", []):
                handle_event(event)

        except requests.RequestException as e:
            log.error(f"Сетевая ошибка: {e}. Повтор через 5 сек...")
            time.sleep(5)
        except Exception as e:
            log.error(f"Неожиданная ошибка: {e}. Повтор через 5 сек...")
            time.sleep(5)


if __name__ == "__main__":
    run_longpoll()
