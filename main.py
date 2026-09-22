import hashlib
import hmac
import json
import os
from urllib.parse import parse_qs, unquote

import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# --- КОНФИГУРАЦИЯ ---
# Токен берём ТОЛЬКО из переменных окружения (никаких значений в коде!)
BOT_TOKEN = os.getenv("MAX_BOT_TOKEN")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "259636193"))

# Флаг для временного отключения валидации (для отладки)
SKIP_VALIDATION = os.getenv("SKIP_VALIDATION", "true").lower() == "true"
# -------------------------------------------------------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def verify_init_data(init_data: str, bot_token: str) -> bool:
    """
    Функция для проверки подлинности данных, пришедших из мини-приложения.
    """
    try:
        params = parse_qs(init_data, keep_blank_values=True)
        received_hash = params.pop('hash', [None])[0]
        if not received_hash:
            return False

        sorted_keys = sorted(params.keys())
        data_check_string_parts = []
        for key in sorted_keys:
            value = params[key][0]
            data_check_string_parts.append(f"{key}={value}")

        data_check_string = "\n".join(data_check_string_parts)

        secret_key = hmac.new(
            "WebAppData".encode(),
            bot_token.encode(),
            hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        return calculated_hash == received_hash
    except Exception as e:
        print(f"Ошибка валидации: {e}")
        return False

def send_message_to_user(user_id: int, text: str):
    """Отправляет сообщение пользователю через API MAX."""
    url = f"https://platform-api2.max.ru/messages?user_id={user_id}"
    headers = {
        "Authorization": BOT_TOKEN,
        "Content-Type": "application/json"
    }
    payload = {
        "text": text,
        "format": "markdown"
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        print(f"=== ОТВЕТ ОТ MAX API === Статус: {response.status_code}, Тело: {response.text}")
        return response.json()
    except Exception as e:
        print(f"=== ОШИБКА ОТПРАВКИ В MAX === {e}")
        return {"ok": False, "error": str(e)}

@app.post("/api/order")
async def receive_order(request: Request):
    """Основной эндпоинт, который принимает заявки от мини-приложения."""
    try:
        data = await request.json()
        print(f"=== ПОЛУЧЕНА ЗАЯВКА === {json.dumps(data, ensure_ascii=False)[:500]}")

        init_data = data.get('initData')
        order_message = data.get('message')

        if not order_message:
            raise HTTPException(status_code=400, detail="Пустое сообщение")

        # 1. Проверяем подлинность данных (можно временно отключить)
        if not SKIP_VALIDATION:
            if not init_data or not verify_init_data(init_data, BOT_TOKEN):
                print("ВНИМАНИЕ: Попытка отправки с невалидными данными!")
                raise HTTPException(status_code=403, detail="Недействительные данные")
        else:
            print("ВНИМАНИЕ: Валидация отключена (SKIP_VALIDATION=true)")

        # 2. Извлекаем user_id из данных
        user_name = 'Клиент'
        user_id = None
        if init_data:
            try:
                params = parse_qs(init_data)
                user_info_str = params.get('user', ['{}'])[0]
                user_info = json.loads(unquote(user_info_str))
                user_id = user_info.get('id')
                user_name = user_info.get('first_name', 'Клиент')
            except Exception as e:
                print(f"Не удалось извлечь данные пользователя: {e}")

        # 3. Формируем финальное сообщение
        if user_id:
            final_message = f"🔥 **Новая заявка от {user_name} (id: {user_id})!**\n\n{order_message}"
        else:
            final_message = f"🔥 **Новая заявка!**\n\n{order_message}"

        # 4. Отправляем сообщение администратору
        print(f"=== ОТПРАВКА АДМИНИСТРАТОРУ (id: {ADMIN_USER_ID}) ===")
        result = send_message_to_user(ADMIN_USER_ID, final_message)
        print(f"=== РЕЗУЛЬТАТ ОТПРАВКИ === {result}")

        return {"status": "ok", "message": "Заявка успешно отправлена"}

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Ошибка при обработке заказа: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

@app.get("/")
async def root():
    return {"status": "ok", "message": "Сервер для приема заявок работает!"}
