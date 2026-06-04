import asyncio
import sys
import datetime
import logging
from telethon import TelegramClient, errors, events, types
import qrcode

# Настройка логирования: пишет и в консоль, и в файл typing_log.txt
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[
        logging.FileHandler("typing_log.txt", encoding="utf-8", mode="a"),
        logging.StreamHandler(sys.stdout)
    ]
)
logging.getLogger('telethon').setLevel(logging.WARNING)

api_id = 11111111  
api_hash = 'qweasdzxc123'
session = 'test'

# Словарь для активных таймеров ожидания. Структура: {user_id: asyncio.Task}
active_typing_tasks = {}

async def get_user_name(client, user_id):
    """Вспомогательная функция для получения имени"""
    try:
        user = await client.get_entity(user_id)
        return f"{user.first_name or ''} {user.last_name or ''}".strip()
    except:
        return f"ID: {user_id}"

async def wait_for_message_timeout(client, user_id, name):
    """Фоновое ожидание: ждем 3 минуты. Если за это время таску не отменили — значит, текст не отправлен"""
    try:
        # Ждем ровно 3 минуты (180 секунд)
        await asyncio.sleep(180)
        
        # Сюда мы добираемся ТОЛЬКО если за 3 минуты не сработал отменяющий триггер (NewMessage)
        time_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logging.info(f"[{time_now}] ⚠️ {name} начал(а) печатать 3 минуты назад, но ТАК И НЕ ОТПРАВИЛ(А) сообщение.")
        
    except asyncio.CancelledError:
        # Сюда мы попадаем, если задача была принудительно отменена. 
        # Человек отправил сообщение в рамках 3 минут — скрипт молча стирает таймер без логов.
        pass
    finally:
        # Убираем себя из списка активных задач
        if active_typing_tasks.get(user_id) == asyncio.current_task():
            active_typing_tasks.pop(user_id, None)

async def main():
    client = TelegramClient(session, api_id, api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        qr = await client.qr_login()
        print("\n📱 Отсканируйте QR-код:")
        print("Telegram → Настройки → Устройства → Добавить устройство\n")

        qr_img = qrcode.QRCode(border=1)
        qr_img.add_data(qr.url)
        qr_img.make(fit=True)

        qr_matrix = qr_img.get_matrix()
        for row in qr_matrix:
            print("".join("██" if cell else "  " for cell in row))

        try:
            await qr.wait()
        except errors.SessionPasswordNeededError:
            print("\n🔒 Двухэтапная верификация активна!")
            password = input("Введите ваш Облачный Пароль (2FA): ")
            await client.sign_in(password=password)

    me = await client.get_me()
    logging.info(f"\n✅ Вы вошли как {me.first_name} ({me.id})")
    logging.info("\n[РЕЖИМ ТИШИНЫ] Скрипт активен. Логируем ТОЛЬКО тех, кто передумал отправлять текст в течение 3 минут.\n")

    # --- ТРИГГЕР 1: ЮЗЕР НАЧАЛ ПЕЧАТАТЬ ---
    @client.on(events.Raw())
    async def handler(update):
        if isinstance(update, types.UpdateUserTyping):
            user_id = update.user_id

            # Если таймер для этого человека еще не запущен — запускаем его
            if user_id is not None and user_id not in active_typing_tasks:
                name = await get_user_name(client, user_id)
                # Создаем фоновую задачу на 3 минуты
                task = asyncio.create_task(wait_for_message_timeout(client, user_id, name))
                active_typing_tasks[user_id] = task

    # --- ТРИГГЕР 2: ЮЗЕР ОТПРАВИЛ СООБЩЕНИЕ ---
    @client.on(events.NewMessage(incoming=True))
    async def message_handler(event):
        if event.is_private:
            user_id = event.sender_id
            
            # Если юзер отправил сообщение, а у нас на него висел таймер — сносим таймер к чертям
            if user_id in active_typing_tasks:
                active_typing_tasks[user_id].cancel()
                active_typing_tasks.pop(user_id, None)
                # Никаких логов здесь нет. Всё прошло в штатном режиме.

    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nСкрипт остановлен.")
