import hashlib
import hmac
import json
import os
from urllib.parse import parse_qs, unquote

import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# --- КОНФИГУРАЦИЯ (ЭТИ ДАННЫЕ НУЖНО БУДЕТ ЗАПОЛНИТЬ) ---
BOT_TOKEN = os.getenv("MAX_BOT_TOKEN", "f9LHodD0cOIzL1jBoRh3RbmA5V7K44WWtL0lW2tb8hYwEBBwx2JBoaa-gQTd95qA3IFEzQVGZathDZGEqPVF")  # Токен вашего бота
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", 259636193))          # Ваш user_id в MAX
# -------------------------------------------------------

app = FastAPI()

# Разрешаем запросы с любого домена (важно для мини-приложения)
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
    Реализует официальный алгоритм валидации MAX.
    """
    try:
        # 1. Разбираем строку initData на пары ключ-значение
        params = parse_qs(init_data, keep_blank_values=True)
        
        # 2. Извлекаем и удаляем hash
        received_hash = params.pop('hash', [None])[0]
        if not received_hash:
            return False
        
        # 3. Сортируем оставшиеся параметры по ключу
        sorted_keys = sorted(params.keys())
        
        # 4. Формируем строку для проверки
        data_check_string_parts = []
        for key in sorted_keys:
            # Берем первое значение для каждого ключа
            value = params[key][0]
            # Убедимся, что значение декодировано (parse_qs обычно делает это сам, но для надежности)
            data_check_string_parts.append(f"{key}={value}")
        
        data_check_string = "\n".join(data_check_string_parts)
        
        # 5. Вычисляем секретный ключ
        secret_key = hmac.new(
            "WebAppData".encode(),
            bot_token.encode(),
            hashlib.sha256
        ).digest()
        
        # 6. Вычисляем подпись
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # 7. Сравниваем
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
        "format": "markdown"  # Можно использовать markdown для красоты
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

@app.post("/api/order")
async def receive_order(request: Request):
    """
    Основной эндпоинт, который принимает заявки от мини-приложения.
    """
    try:
        data = await request.json()
        
        # Извлекаем данные, которые прислал клиент
        init_data = data.get('initData')
        order_message = data.get('message')
        
        if not init_data or not order_message:
            raise HTTPException(status_code=400, detail="Неверные данные запроса")
        
        # 1. Проверяем подлинность данных
        if not verify_init_data(init_data, BOT_TOKEN):
            print("ВНИМАНИЕ: Попытка отправки с невалидными данными!")
            raise HTTPException(status_code=403, detail="Недействительные данные")
        
        # 2. Извлекаем user_id из проверенных данных
        params = parse_qs(init_data)
        user_info_str = params.get('user', ['{}'])[0]
        user_info = json.loads(unquote(user_info_str))
        user_id = user_info.get('id')
        user_name = user_info.get('first_name', 'Клиент')
        
        if not user_id:
            raise HTTPException(status_code=400, detail="Не удалось определить пользователя")
        
        # 3. Формируем финальное сообщение для администратора
        final_message = (
            f"🔥 **Новая заявка от {user_name}!**\n\n"
            f"{order_message}"
        )
        
        # 4. Отправляем сообщение администратору
        # ВАЖНО: Замените ADMIN_USER_ID на ваш личный ID в MAX
        if ADMIN_USER_ID:
            send_message_to_user(259636193, final_message)
        else:
            print("ADMIN_USER_ID не настроен. Сообщение не отправлено.")
            
        # Можно также отправить подтверждение клиенту
        # send_message_to_user(user_id, "Спасибо! Ваша заявка принята, мы свяжемся с вами.")
        
        return {"status": "ok", "message": "Заявка успешно отправлена"}
        
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Ошибка при обработке заказа: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

@app.get("/")
async def root():
    """Проверка, что сервер жив."""
    return {"status": "ok", "message": "Сервер для приема заявок работает!"}
