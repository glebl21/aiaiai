"""
VK AI Bot — Long Poll версия с поддержкой фото
"""

import requests
import time
import base64
import logging
from config import (
    VK_TOKEN, VK_GROUP_ID, VK_API_VERSION,
    GROQ_API_KEY, AI_SYSTEM_PROMPT, MAX_HISTORY_MESSAGES
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

dialog_history = {}


# ─────────────────────────── VK API ───────────────────────────

def vk_call(method, params):
    params["access_token"] = VK_TOKEN
    params["v"] = VK_API_VERSION
    resp = requests.post(f"https://api.vk.com/method/{method}", data=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"VK API error {data['error']['error_code']}: {data['error']['error_msg']}")
    return data.get("response", {})


def send_message(user_id, text):
    vk_call("messages.send", {
        "user_id": user_id,
        "message": text,
        "random_id": int(time.time() * 1000),
    })
    log.info(f"→ [{user_id}] {text[:80]}{'...' if len(text) > 80 else ''}")


def get_longpoll_server():
    return vk_call("groups.getLongPollServer", {"group_id": VK_GROUP_ID})


def get_best_photo_url(photo):
    """Получить URL фото максимального размера."""
    sizes = photo.get("sizes", [])
    if not sizes:
        return None
    # Сортируем по ширине и берём наибольшее
    sizes_sorted = sorted(sizes, key=lambda s: s.get("width", 0), reverse=True)
    return sizes_sorted[0].get("url")


def download_image_base64(url):
    """Скачать фото и закодировать в base64."""
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return base64.b64encode(resp.content).decode("utf-8")


# ─────────────────────────── AI (Groq) ───────────────────────────

def ask_groq(user_id, user_text, image_b64=None):
    """Groq — текст + фото (если есть)."""
    history = dialog_history.setdefault(user_id, [])

    # Формируем контент текущего сообщения
    if image_b64:
        # Мультимодальный запрос с фото
        content = [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{image_b64}"
                }
            }
        ]
        if user_text:
            content.append({"type": "text", "text": user_text})
        else:
            content.append({"type": "text", "text": "Опиши что на этом фото."})
        model = "meta-llama/llama-4-scout-17b-16e-instruct"
    else:
        content = user_text
        model = "llama-3.3-70b-versatile"

    history.append({"role": "user", "content": content})

    if len(history) > MAX_HISTORY_MESSAGES * 2:
        history[:] = history[-MAX_HISTORY_MESSAGES * 2:]

    # Для истории с картинками оставляем только текстовые сообщения
    # (Groq не принимает картинки в истории, только в последнем сообщении)
    text_history = []
    for msg in history[:-1]:
        if isinstance(msg["content"], list):
            # Извлекаем только текст из мультимодальных сообщений
            texts = [p["text"] for p in msg["content"] if p.get("type") == "text"]
            text_history.append({"role": msg["role"], "content": " ".join(texts)})
        else:
            text_history.append(msg)

    messages = [{"role": "system", "content": AI_SYSTEM_PROMPT}] + text_history + [history[-1]]

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "max_tokens": 1024,
        },
        timeout=30,
    )
    resp.raise_for_status()
    answer = resp.json()["choices"][0]["message"]["content"]
    history.append({"role": "assistant", "content": answer})
    return answer


# ─────────────────────────── Обработка событий ───────────────────────────

def handle_event(event):
    if event.get("type") != "message_new":
        return

    msg = event.get("object", {}).get("message", {})
    user_id = msg.get("from_id")
    text = msg.get("text", "").strip()
    attachments = msg.get("attachments", [])

    if user_id <= 0:
        return

    # Пропускаем если нет ни текста ни вложений
    if not text and not attachments:
        return

    log.info(f"← [{user_id}] {text or '(фото)'} | вложений: {len(attachments)}")

    if text.lower() in ("/reset", "сброс", "/start"):
        dialog_history.pop(user_id, None)
        send_message(user_id, "История диалога очищена. Начнём заново! 👋")
        return

    try:
        vk_call("messages.setActivity", {"user_id": user_id, "type": "typing", "group_id": VK_GROUP_ID})

        # Ищем фото среди вложений
        image_b64 = None
        for att in attachments:
            if att.get("type") == "photo":
                photo_url = get_best_photo_url(att["photo"])
                if photo_url:
                    log.info(f"   Скачиваю фото: {photo_url[:60]}...")
                    image_b64 = download_image_base64(photo_url)
                    log.info(f"   Фото скачано, размер base64: {len(image_b64)} символов")
                break  # берём только первое фото

        answer = ask_groq(user_id, text, image_b64=image_b64)
        send_message(user_id, answer)

    except requests.HTTPError as e:
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        log.error(f"HTTP ошибка от [{user_id}]: {e} | {detail}")
        send_message(user_id, "Произошла ошибка. Попробуйте ещё раз чуть позже 🙏")
    except Exception as e:
        log.error(f"Ошибка от [{user_id}]: {e}")
        send_message(user_id, "Произошла ошибка. Попробуйте ещё раз чуть позже 🙏")


# ─────────────────────────── Long Poll цикл ───────────────────────────

def run_longpoll():
    log.info("🤖 VK AI Bot запускается...")
    log.info(f"   Группа: {VK_GROUP_ID}")
    log.info(f"   AI: GROQ (текст + фото)")

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
            updates = data.get("updates", [])
            if updates:
                log.info(f"📨 Получено событий: {len(updates)}")
                for event in updates:
                    handle_event(event)

        except requests.RequestException as e:
            log.error(f"Сетевая ошибка: {e}. Повтор через 5 сек...")
            time.sleep(5)
        except Exception as e:
            log.error(f"Неожиданная ошибка: {e}. Повтор через 5 сек...")
            time.sleep(5)


if __name__ == "__main__":
    run_longpoll()
